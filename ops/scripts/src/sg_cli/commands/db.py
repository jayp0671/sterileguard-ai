"""sg db: migrations, reset, seed, types and lint through the Supabase CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import typer

from sg_cli import core

app = typer.Typer(no_args_is_help=True)

SUPABASE = ["pnpm", "exec", "supabase"]
LOCAL_DB_URL = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
ENV_DB_VARS = {"staging": "SUPABASE_DB_URL_STAGING", "prod": "SUPABASE_DB_URL_PROD"}
Env = Literal["local", "staging", "prod"]


def pending_migrations(root: Path) -> list[str]:
    folder = root / "supabase" / "migrations"
    return sorted(p.name for p in folder.glob("*.sql"))


def db_url(env: str) -> str:
    if env == "local":
        return LOCAL_DB_URL
    var = ENV_DB_VARS[env]
    return core.require_env(var)[var]


@app.command("migrate", help="Apply pending migrations to local, staging or prod.")
def migrate(
    env: str = typer.Option("local", "--env", help="local | staging | prod"),
    confirm: bool = typer.Option(False, "--confirm", help="Required for prod."),
) -> None:
    result = core.Result("db", "migrate")
    if env not in ("local", "staging", "prod"):
        raise typer.BadParameter("env must be local, staging or prod")
    result.data["env"] = env
    if env == "local":
        core.run([*SUPABASE, "migration", "up", "--local"])
    else:
        url = db_url(env)
        result.add(f"migrations in repo: {', '.join(pending_migrations(core.repo_root()))}")
        core.run([*SUPABASE, "db", "push", "--db-url", url, "--dry-run"])
        if env == "prod" and not confirm:
            result.ok = False
            result.add("prod: review the pending migrations above, then rerun with --confirm")
        else:
            core.run([*SUPABASE, "db", "push", "--db-url", url])
            result.add(f"{env} migrated")
    result.finish()


@app.command("reset", help="Local only: recreate the database from migrations and seed.")
def reset() -> None:
    result = core.Result("db", "reset")
    code, _ = core.capture([*SUPABASE, "status"])
    if code != 0 and not core.OPTIONS.dry_run:
        result.add("local Supabase is not running: start Docker, then `pnpm exec supabase start`")
        result.ok = False
    else:
        core.run([*SUPABASE, "db", "reset", "--local"])
        result.add("local database reset with migrations and seed")
    result.finish()


@app.command("seed", help="Re-run supabase/seed.sql on the local database.")
def seed() -> None:
    result = core.Result("db", "seed")
    core.run(["psql", LOCAL_DB_URL, "-v", "ON_ERROR_STOP=1", "-f", "supabase/seed.sql"])
    result.add("seed applied (idempotent)")
    result.finish()


@app.command("types", help="Generate packages/contracts/src/db.ts from the local schema.")
def types() -> None:
    result = core.Result("db", "types")
    out = core.repo_root() / "packages" / "contracts" / "src" / "db.ts"
    if core.OPTIONS.dry_run:
        core.run([*SUPABASE, "gen", "types", "typescript", "--local"])
    else:
        code, text = core.capture([*SUPABASE, "gen", "types", "typescript", "--local"])
        if code != 0:
            raise core.CommandError(["supabase", "gen", "types"], code)
        out.write_text(text.rstrip() + "\n", encoding="utf-8", newline="\n")
    result.add(f"wrote {out.relative_to(core.repo_root())}")
    result.finish()


@app.command("lint", help="supabase db lint; fails on error-level findings.")
def lint(env: str = typer.Option("local", "--env")) -> None:
    result = core.Result("db", "lint")
    target = ["--local"] if env == "local" else ["--db-url", db_url(env)]
    code = core.run(
        [*SUPABASE, "db", "lint", *target, "--level", "warning", "--fail-on", "error"],
        check=False,
    )
    result.ok = code == 0
    result.add("lint clean" if result.ok else "lint found errors")
    result.finish()


@app.command("rls-test", help="Run the pgTAP tests in supabase/tests.")
def rls_test() -> None:
    result = core.Result("db", "rls-test")
    result.ok = core.run([*SUPABASE, "test", "db"], check=False) == 0
    result.finish()


def _later(name: str) -> None:
    result = core.Result("db", name)
    result.data.update(implemented=False, ticket="SG-30")
    result.add(f"sg db {name}: not implemented yet, see SG-30")
    result.finish()


@app.command("backup", help="Not implemented yet, see SG-30.")
def backup() -> None:
    _later("backup")


@app.command("restore", help="Not implemented yet, see SG-30.")
def restore() -> None:
    _later("restore")
