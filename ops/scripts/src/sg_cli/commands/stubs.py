"""Placeholder groups from plan §16. Each command names the ticket that builds it."""

from __future__ import annotations

from collections.abc import Callable

import typer

from sg_cli import core

# group -> (ticket, help, commands)
STUBS: dict[str, tuple[str, str, list[str]]] = {
    "db": (
        "SG-03",
        "Database migrations, seed, types, lint.",
        ["migrate", "reset", "seed", "types", "lint", "rls-test", "backup", "restore"],
    ),
    "sim": ("SG-09", "SimPy simulator.", ["run", "calibrate", "scenario-grid", "validate"]),
    "data": (
        "SG-21",
        "Data import pipeline.",
        ["import", "profile", "validate", "report", "synth-messy"],
    ),
    "ml": (
        "SG-13",
        "Model training and registry.",
        [
            "train",
            "evaluate",
            "compare",
            "explain",
            "register",
            "activate",
            "rollback",
            "drift",
            "model-card",
        ],
    ),
    "test": (
        "SG-05",
        "Test runners for every layer.",
        [
            "unit",
            "api",
            "db",
            "e2e",
            "visual",
            "a11y",
            "load",
            "security",
            "i18n",
            "agents",
            "affected",
            "all",
        ],
    ),
    "fix": ("SG-30", "Autofix loop.", ["run", "report"]),
    "i18n": ("SG-27", "Translations.", ["extract", "translate", "check", "pseudo"]),
    "compliance": ("SG-28", "Compliance checks.", ["check", "licenses"]),
    "docs": ("SG-30", "Docs tooling.", ["api", "diagrams", "plan-sync"]),
    "contracts": ("SG-02", "OpenAPI spec and generated TS types.", ["gen", "check"]),
    "release": (
        "SG-34",
        "Release tooling.",
        ["version", "changelog", "deploy", "smoke", "rollback"],
    ),
    "ops": ("SG-30", "Operations.", ["keepalive", "status", "health", "report"]),
    "demo": ("SG-16", "Demo data.", ["seed-demo", "reset-demo"]),
}


def _make(group: str, name: str, ticket: str) -> Callable[[], None]:
    def _stub() -> None:
        result = core.Result(group, name)
        result.data.update(implemented=False, ticket=ticket)
        result.add(f"sg {group} {name}: not implemented yet, see {ticket}")
        result.finish()

    return _stub


def stub_group(group: str, sub: typer.Typer | None = None) -> typer.Typer:
    """Add stub commands for `group` to `sub` (new if None), skipping names already defined."""
    ticket, help_text, commands = STUBS[group]
    sub = sub or typer.Typer(help=f"{help_text} (built by {ticket})", no_args_is_help=True)
    defined = {c.name for c in sub.registered_commands}
    for name in commands:
        if name not in defined:
            sub.command(name, help=f"Not implemented yet, see {ticket}.")(
                _make(group, name, ticket)
            )
    return sub


def register(app: typer.Typer, implemented: dict[str, typer.Typer] | None = None) -> None:
    """Register every group; real sub-apps in `implemented` get stubs for their missing commands."""
    implemented = implemented or {}
    for group in STUBS:
        ticket, help_text, _ = STUBS[group]
        real = implemented.get(group)
        if real is not None:
            app.add_typer(stub_group(group, real), name=group, help=help_text)
        else:
            app.add_typer(stub_group(group), name=group, help=f"{help_text} (built by {ticket})")
