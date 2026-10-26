"""sg: the SterileGuard command line. Every group is registered here."""

from __future__ import annotations

import sys
from typing import Any

import typer

from sg_cli import core
from sg_cli.commands import (
    bootstrap,
    contracts,
    db,
    dev,
    doctor,
    memory,
    ml,
    sim,
    stubs,
    testing,
)

GLOBAL_FLAGS = ("--dry-run", "--json")


def hoist_flags(argv: list[str]) -> list[str]:
    """Move global flags to the front so `sg doctor --json` equals `sg --json doctor`."""
    return [a for a in argv if a in GLOBAL_FLAGS] + [a for a in argv if a not in GLOBAL_FLAGS]


class SgTyper(typer.Typer):
    """Typer app that accepts --dry-run and --json anywhere on the command line."""

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        sys.argv = [sys.argv[0], *hoist_flags(sys.argv[1:])]
        return super().__call__(*args, **kwargs)


app = SgTyper(
    help="SterileGuard AI developer CLI. Every command supports --dry-run and --json.",
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_enable=False,
)


@app.callback()
def _global(
    dry_run: bool = typer.Option(False, "--dry-run", help="Print planned actions only."),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output for agents."),
) -> None:
    core.OPTIONS.dry_run = dry_run
    core.OPTIONS.json = json_out


app.command("doctor", help="Check tools, versions and env vars.")(doctor.doctor)
app.command("bootstrap", help="Install everything and prepare a local stack.")(bootstrap.bootstrap)
app.command("dev", help="Run Supabase, web (3000) and API (8000) together.")(dev.dev)
app.add_typer(memory.app, name="memory", help="Repo memory: sync, handoff, adr, task.")
stubs.register(
    app,
    implemented={
        "contracts": contracts.app,
        "db": db.app,
        "ml": ml.app,
        "sim": sim.app,
        "test": testing.app,
    },
)


if __name__ == "__main__":
    app()
