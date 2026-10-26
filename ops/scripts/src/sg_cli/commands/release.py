"""sg release (SG-16 smoke; the rest of release tooling is SG-34)."""

from __future__ import annotations

import typer

from sg_cli import core

app = typer.Typer(no_args_is_help=True)


@app.command("smoke", help="Sign-in page loads; API /health ok; /ready ok with a model version.")
def smoke(env: str = typer.Option("staging", "--env", help="staging | prod")) -> None:
    if env not in ("staging", "prod"):
        raise typer.BadParameter("--env must be staging or prod")
    suffix = env.upper()
    found = core.require_env(f"WEB_URL_{suffix}", f"API_URL_{suffix}")
    result = core.Result("release", "smoke")
    core.run(
        [
            "pnpm",
            "--filter",
            "@sg/web",
            "exec",
            "playwright",
            "test",
            "e2e/smoke.spec.ts",
            "--project=chromium",
        ],
        env={
            "E2E_BASE_URL": found[f"WEB_URL_{suffix}"].rstrip("/"),
            "SMOKE_API_URL": found[f"API_URL_{suffix}"].rstrip("/"),
        },
    )
    result.data.update(env=env)
    result.add(f"smoke passed on {env}")
    result.finish()
