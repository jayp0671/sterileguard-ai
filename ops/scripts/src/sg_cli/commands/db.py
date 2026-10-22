"""sg db: migrations, reset, seed, types and lint through the Supabase CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import typer

from sg_cli import core

app = typer.Typer(no_args_is_help=True)

SUPABASE = ["pnpm", "exec", "supabase"]
LOCAL_DB_URL = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
# Which variable each --env reads. Local tools never read a *_STAGING / *_PROD name, and a hosted
# URL is refused for local, so a local command can never touch the hosted database.
ENV_DB_VARS = {
    "local": "SUPABASE_DB_URL",
    "staging": "SUPABASE_DB_URL_STAGING",
    "prod": "SUPABASE_DB_URL_PROD",
}
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "host.docker.internal"}
Env = Literal["local", "staging", "prod"]


def pending_migrations(root: Path) -> list[str]:
    folder = root / "supabase" / "migrations"
    return sorted(p.name for p in folder.glob("*.sql"))


def is_local_url(url: str) -> bool:
    return (urlsplit(url).hostname or "") in LOCAL_HOSTS


def db_url(env: str) -> str:
    """Database URL for an environment, with guards against crossing local and hosted."""
    if env not in ENV_DB_VARS:
        raise typer.BadParameter("env must be local, staging or prod")
    var = ENV_DB_VARS[env]
    if env == "local":
        url = core.env_value(var) or LOCAL_DB_URL
        if not is_local_url(url):
            raise SystemExit(f"{var} must point at the local stack (127.0.0.1), not a hosted DB")
        return url
    url = core.require_env(var)[var]
    if is_local_url(url):
        raise SystemExit(f"{var} points at localhost; expected the hosted {env} database")
    return url


def redact(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.username}:***@{parts.hostname}:{parts.port}{parts.path}"


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


@app.command("seed", help="Re-run supabase/seed.sql on local or staging (never prod).")
def seed(env: str = typer.Option("local", "--env", help="local | staging")) -> None:
    result = core.Result("db", "seed")
    if env == "prod":
        raise typer.BadParameter("seed.sql is for local and staging only")
    url = db_url(env)
    result.add(f"- seed {env} ({redact(url)})")
    if not core.OPTIONS.dry_run:
        import psycopg

        sql = (core.repo_root() / "supabase" / "seed.sql").read_text(encoding="utf-8")
        with psycopg.connect(url, autocommit=True, connect_timeout=15) as conn:
            conn.execute(sql.encode("utf-8"))
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


@app.command("rls-test", help="Run the pgTAP tests in supabase/tests (local or staging).")
def rls_test(
    env: str = typer.Option("local", "--env", help="local | staging"),
    runner: str = typer.Option(
        "auto", "--runner", help="auto | cli (supabase test db, needs Docker) | python (psycopg)"
    ),
) -> None:
    """Every test file runs inside begin ... rollback, so staging is left unchanged."""
    import time

    from sg_cli.commands.testing import record

    result = core.Result("db", "rls-test")
    if env == "prod":
        raise typer.BadParameter("never run tests against prod")
    url = db_url(env)
    use_cli = runner == "cli" or (
        runner == "auto" and env == "local" and core.capture([*SUPABASE, "status"])[0] == 0
    )
    start = time.perf_counter()
    if use_cli:
        target = [] if env == "local" else ["--db-url", url]
        code = core.run([*SUPABASE, "test", "db", *target], check=False)
        counts = {"passed": int(code == 0), "failed": int(code != 0), "skipped": 0}
        result.ok = code == 0
    elif core.OPTIONS.dry_run:
        result.add(f"would run pgTAP files in supabase/tests against {redact(url)}")
        counts = {"passed": 0, "failed": 0, "skipped": 0}
    else:
        from sg_cli import pgtap

        files = pgtap.run_dir(url, core.repo_root() / "supabase" / "tests")
        for f in files:
            status = "ok" if f.ok else "FAIL"
            result.add(
                f"- {status} {f.name}: {f.passed} passed, {f.failed} failed, plan {f.planned}"
            )
            for line in f.lines:
                if line.startswith("not ok"):
                    result.add(f"    {line}")
            if f.error:
                result.add(f"    error: {core.redact_secrets(f.error)}")
        counts = {
            "passed": sum(f.passed for f in files),
            "failed": sum(f.failed + (1 if f.error else 0) for f in files),
            "skipped": 0,
        }
        result.ok = bool(files) and all(f.ok for f in files)
    if not core.OPTIONS.dry_run:
        record(f"db-{env}", counts, time.perf_counter() - start)
    result.data.update(env=env, **counts)
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
