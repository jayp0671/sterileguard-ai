"""sg deploy staging (SG-16): one command that wires and deploys the staging environment.

Run by a person (Jay) on a machine where the Hugging Face, Vercel and GitHub CLIs are signed in.
It reads values from .env and those logins, sends them straight to each service's secret store,
and never prints a secret. Every step is idempotent, so it is safe to run again.

  1. Hugging Face: create the Docker Space, set its variables and secrets, upload the API.
  2. Vercel: Root Directory apps/web (Next.js), environment variables, a production deploy.
  3. GitHub: the secrets and variables the deploy-api, keepalive and e2e workflows read.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import typer

from sg_cli import core

app = typer.Typer(no_args_is_help=True)

SPACE_ID = "jayp671/sterileguard-api"
API_URL = "https://jayp671-sterileguard-api.hf.space"
VERCEL_PROJECT = "sterileguard-ai"
VERCEL_SCOPE = "jays-projects-8a6490ad"
PREVIEW_REGEX = r"^https://sterileguard-ai-[a-z0-9-]+-jays-projects-8a6490ad\.vercel\.app$"
VERCEL_API = "https://api.vercel.com"


def _env(name: str) -> str:
    value = core.env_value(name)
    if not value:
        raise SystemExit(f"{name} is not set in .env")
    return value


def _ensure_internal_token(root: Path) -> str:
    """INTERNAL_TOKEN_STAGING: generated once and kept in .env (gitignored)."""
    existing = core.env_value("INTERNAL_TOKEN_STAGING")
    if existing:
        return existing
    token = secrets.token_urlsafe(32)
    with (root / ".env").open("a", encoding="utf-8") as f:
        f.write(f"\nINTERNAL_TOKEN_STAGING={token}\n")
    return token


def _ensure_urls(root: Path) -> None:
    """WEB_URL_STAGING and API_URL_STAGING for sg release smoke (not secrets)."""
    missing = {
        k: v
        for k, v in {"WEB_URL_STAGING": _web_url(), "API_URL_STAGING": API_URL}.items()
        if not core.env_value(k)
    }
    if missing:
        with (root / ".env").open("a", encoding="utf-8") as f:
            f.writelines(f"{k}={v}\n" for k, v in missing.items())


# ---------------------------------------------------------------------------
# Hugging Face
# ---------------------------------------------------------------------------


def huggingface(result: core.Result, root: Path, internal_token: str, sha: str) -> None:
    from huggingface_hub import HfApi

    api = HfApi()
    api.create_repo(SPACE_ID, repo_type="space", space_sdk="docker", exist_ok=True)
    supabase_url = _env("SUPABASE_URL_STAGING").rstrip("/")
    variables = {
        "ENV": "staging",
        "SUPABASE_URL": supabase_url,
        "SUPABASE_JWKS_URL": f"{supabase_url}/auth/v1/.well-known/jwks.json",
        "CORS_ORIGINS": f"{_web_url()},http://localhost:3000",
        "CORS_ORIGIN_REGEX": PREVIEW_REGEX,
        "MODEL_BUCKET": "models",
    }
    for key, value in variables.items():
        api.add_space_variable(SPACE_ID, key, value)
    space_secrets = {
        "SUPABASE_ANON_KEY": _env("SUPABASE_ANON_KEY_STAGING"),
        "SUPABASE_SERVICE_ROLE_KEY": _env("SUPABASE_SERVICE_ROLE_KEY_STAGING"),
        "INTERNAL_TOKEN": internal_token,
    }
    for key, value in space_secrets.items():
        api.add_space_secret(SPACE_ID, key, value)
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / "space"
        bash = shutil.which("bash") or "bash"
        subprocess.run(
            [bash, str(root / "ops/deploy/space/stage.sh"), stage.as_posix(), sha], check=True
        )
        api.upload_folder(
            folder_path=str(stage),
            repo_id=SPACE_ID,
            repo_type="space",
            commit_message=f"Deploy {sha[:12]}",
            delete_patterns="*",
        )
    result.add(
        f"Hugging Face: Space {SPACE_ID} configured ({len(variables)} variables, "
        f"{len(space_secrets)} secrets) and API {sha[:7]} uploaded; it builds in a few minutes"
    )


# ---------------------------------------------------------------------------
# Vercel
# ---------------------------------------------------------------------------


def _vercel_token() -> str:
    for base in (os.environ.get("APPDATA"), os.path.expanduser("~/.local/share")):
        if not base:
            continue
        for sub in ("com.vercel.cli/Data/auth.json", "com.vercel.cli/auth.json"):
            path = Path(base) / sub
            if path.exists():
                token = json.loads(path.read_text(encoding="utf-8")).get("token")
                if token:
                    return str(token)
    raise SystemExit("Vercel CLI login not found: run `npx vercel login` first")


def _vercel(method: str, path: str, body: Any = None) -> Any:
    import httpx

    resp = httpx.request(
        method,
        f"{VERCEL_API}{path}",
        params={"slug": VERCEL_SCOPE},
        json=body,
        headers={"Authorization": f"Bearer {_vercel_token()}"},
        timeout=60.0,
    )
    if resp.status_code >= 400:
        raise SystemExit(f"Vercel {method} {path.split('?')[0]} failed ({resp.status_code})")
    return resp.json() if resp.content else None


def _web_url() -> str:
    return (core.env_value("WEB_URL_STAGING") or f"https://{VERCEL_PROJECT}.vercel.app").rstrip("/")


def vercel(result: core.Result, root: Path) -> None:
    _vercel(
        "PATCH",
        f"/v9/projects/{VERCEL_PROJECT}",
        {"rootDirectory": "apps/web", "framework": "nextjs", "nodeVersion": "24.x"},
    )
    public = {
        "NEXT_PUBLIC_SUPABASE_URL": _env("SUPABASE_URL_STAGING").rstrip("/"),
        "NEXT_PUBLIC_SUPABASE_ANON_KEY": _env("SUPABASE_ANON_KEY_STAGING"),
        "NEXT_PUBLIC_API_URL": API_URL,
        "NEXT_PUBLIC_SITE_URL": _web_url(),
        "NEXT_PUBLIC_APP_ENV": "staging",
    }
    turnstile = core.env_value("NEXT_PUBLIC_TURNSTILE_SITE_KEY")
    if turnstile:
        public["NEXT_PUBLIC_TURNSTILE_SITE_KEY"] = turnstile
    _vercel(
        "POST",
        f"/v10/projects/{VERCEL_PROJECT}/env?upsert=true",
        [
            {"key": k, "value": v, "type": "plain", "target": ["production", "preview"]}
            for k, v in public.items()
        ],
    )
    result.add(f"Vercel: Root Directory apps/web, {len(public)} environment variables set")
    npx = shutil.which("npx") or "npx"
    core.run(
        [
            npx,
            "-y",
            "vercel@latest",
            "link",
            "--yes",
            "--project",
            VERCEL_PROJECT,
            "--scope",
            VERCEL_SCOPE,
        ],
        cwd=root,
    )
    core.run(
        [npx, "-y", "vercel@latest", "deploy", "--prod", "--yes", "--scope", VERCEL_SCOPE],
        cwd=root,
    )
    result.add(f"Vercel: production deploy started for {_web_url()}")


# ---------------------------------------------------------------------------
# GitHub
# ---------------------------------------------------------------------------


def github(result: core.Result) -> None:
    from huggingface_hub import get_token

    gh = shutil.which("gh") or "gh"
    hf_token = get_token()
    gh_secrets = {"SUPABASE_DB_URL_STAGING": _env("SUPABASE_DB_URL_STAGING")}
    if hf_token:
        gh_secrets["HF_TOKEN"] = hf_token
    for key, value in gh_secrets.items():
        subprocess.run(
            [gh, "secret", "set", key], input=value, text=True, check=True, capture_output=True
        )
    gh_vars = {"HF_SPACE_ID": SPACE_ID, "API_URL": API_URL}
    for key, value in gh_vars.items():
        subprocess.run(
            [gh, "variable", "set", key, "--body", value], check=True, capture_output=True
        )
    result.add(f"GitHub: secrets {sorted(gh_secrets)} and variables {sorted(gh_vars)} set")


@app.command("staging", help="Configure and deploy staging (HF Space, Vercel, GitHub).")
def staging(
    skip_hf: bool = typer.Option(False, "--skip-hf"),
    skip_vercel: bool = typer.Option(False, "--skip-vercel"),
    skip_github: bool = typer.Option(False, "--skip-github"),
) -> None:
    result = core.Result("deploy", "staging")
    if core.OPTIONS.dry_run:
        result.add("would configure the HF Space, Vercel project and GitHub secrets, then deploy")
        result.finish()
        return
    root = core.repo_root()
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True
    ).stdout.strip()
    token = _ensure_internal_token(root)
    _ensure_urls(root)
    if not skip_hf:
        huggingface(result, root, token, sha)
    if not skip_github:
        github(result)
    if not skip_vercel:
        vercel(result, root)
    result.add(f"Next: wait for {API_URL}/ready, then `uv run sg release smoke --env staging`")
    result.finish()
