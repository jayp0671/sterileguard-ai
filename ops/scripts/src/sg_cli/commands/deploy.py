"""sg deploy staging (SG-16): wire and deploy the staging web app.

Run by a person (Jay) on a machine where the Vercel and GitHub CLIs are signed in. It reads values
from .env and those logins, sends them straight to each service, and never prints a secret.
Every step is idempotent, so it is safe to run again.

  1. GitHub: the secrets and variables the keepalive and e2e workflows read.
  2. Vercel: Root Directory apps/web (Next.js), environment variables, a production deploy.

The API runs on Render (render.yaml, ADR-0007), created once from the Render dashboard.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import typer

from sg_cli import core

app = typer.Typer(no_args_is_help=True)

API_URL = "https://sterileguard-api.onrender.com"
VERCEL_PROJECT = "sterileguard-ai"
VERCEL_SCOPE = "jays-projects-8a6490ad"
VERCEL_API = "https://api.vercel.com"


def _env(name: str) -> str:
    value = core.env_value(name)
    if not value:
        raise SystemExit(f"{name} is not set in .env")
    return value


def _api_url() -> str:
    return (core.env_value("API_URL_STAGING") or API_URL).rstrip("/")


def _web_url() -> str:
    return (core.env_value("WEB_URL_STAGING") or f"https://{VERCEL_PROJECT}.vercel.app").rstrip("/")


def _ensure_urls(root: Path) -> None:
    """WEB_URL_STAGING and API_URL_STAGING for sg release smoke (not secrets)."""
    wanted = {"WEB_URL_STAGING": _web_url(), "API_URL_STAGING": API_URL}
    current = {k: core.env_value(k) for k in wanted}
    path = root / ".env"
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    # A Hugging Face URL from the first attempt is replaced by the Render one.
    lines = [ln for ln in lines if not (ln.startswith("API_URL_STAGING=") and "hf.space" in ln)]
    for key, value in wanted.items():
        if not current[key] or (key == "API_URL_STAGING" and "hf.space" in (current[key] or "")):
            lines.append(f"{key}={value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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


def vercel(result: core.Result, root: Path) -> None:
    _vercel(
        "PATCH",
        f"/v9/projects/{VERCEL_PROJECT}",
        {"rootDirectory": "apps/web", "framework": "nextjs", "nodeVersion": "24.x"},
    )
    public = {
        "NEXT_PUBLIC_SUPABASE_URL": _env("SUPABASE_URL_STAGING").rstrip("/"),
        "NEXT_PUBLIC_SUPABASE_ANON_KEY": _env("SUPABASE_ANON_KEY_STAGING"),
        "NEXT_PUBLIC_API_URL": _api_url(),
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
    gh = shutil.which("gh") or "gh"
    gh_secrets = {"SUPABASE_DB_URL_STAGING": _env("SUPABASE_DB_URL_STAGING")}
    for key, value in gh_secrets.items():
        subprocess.run(
            [gh, "secret", "set", key], input=value, text=True, check=True, capture_output=True
        )
    gh_vars = {"API_URL": _api_url()}
    for key, value in gh_vars.items():
        subprocess.run(
            [gh, "variable", "set", key, "--body", value], check=True, capture_output=True
        )
    result.add(f"GitHub: secrets {sorted(gh_secrets)} and variables {sorted(gh_vars)} set")


@app.command("staging", help="Configure GitHub and Vercel for staging, then deploy the web app.")
def staging(
    skip_vercel: bool = typer.Option(False, "--skip-vercel"),
    skip_github: bool = typer.Option(False, "--skip-github"),
) -> None:
    result = core.Result("deploy", "staging")
    if core.OPTIONS.dry_run:
        result.add("would set GitHub secrets and the Vercel project, then deploy the web app")
        result.finish()
        return
    root = core.repo_root()
    _ensure_urls(root)
    if not skip_github:
        github(result)
    if not skip_vercel:
        vercel(result, root)
    result.add(f"Next: wait for {_api_url()}/ready, then `uv run sg release smoke --env staging`")
    result.finish()
