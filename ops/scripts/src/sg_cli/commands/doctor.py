"""sg doctor: check tools, versions and env vars, with a fix hint per row."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from rich.table import Table

from sg_cli import core


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    hint: str
    required: bool = True


def node_matches(nvmrc: str, node_output: str) -> bool:
    """True when `node --version` has the major version pinned in .nvmrc ('24' or 'lts/*')."""
    wanted = core.parse_version(nvmrc.strip() + ".0")
    got = core.parse_version(node_output)
    if wanted is None:  # e.g. lts/*: accept any even-numbered (LTS) major
        return got is not None and got[0] % 2 == 0
    return got is not None and got[0] == wanted[0]


def python_ok(output: str, wanted: str = "3.12") -> bool:
    got = core.parse_version(output)
    want = core.parse_version(wanted)
    return got is not None and want is not None and got[:2] == want[:2]


def _tool(name: str, cmd: list[str], hint: str, required: bool = True) -> Check:
    code, out = core.capture(cmd)
    first = out.splitlines()[0] if out else ""
    return Check(name, code == 0, first if code == 0 else "not found", hint, required)


def collect() -> list[Check]:
    root = core.repo_root()
    checks: list[Check] = [_tool("git", ["git", "--version"], "Install git: https://git-scm.com")]

    nvmrc = (root / ".nvmrc").read_text(encoding="utf-8").strip()
    code, out = core.capture(["node", "--version"])
    checks.append(
        Check(
            "node",
            code == 0 and node_matches(nvmrc, out),
            out if code == 0 else "not found",
            f"Install Node {nvmrc} (nvm install {nvmrc}, or nvm-windows / fnm)",
        )
    )
    checks.append(_tool("pnpm", ["pnpm", "--version"], "corepack enable && corepack prepare"))
    checks.append(_tool("uv", ["uv", "--version"], "Install uv: https://docs.astral.sh/uv/"))

    code, out = core.capture(["uv", "run", "--no-project", "--python", "3.12", "python", "-V"])
    checks.append(
        Check(
            "python 3.12",
            code == 0 and python_ok(out),
            out or "not found",
            "uv python install 3.12",
        )
    )

    code, out = core.capture(["docker", "info", "--format", "{{.ServerVersion}}"])
    checks.append(
        Check(
            "docker running",
            code == 0,
            f"server {out}" if code == 0 else "daemon not reachable",
            "Start Docker Desktop (needed for the local Supabase stack)",
        )
    )

    code, out = core.capture(["supabase", "--version"])
    if code != 0:
        code, out = core.capture(["pnpm", "exec", "supabase", "--version"])
    checks.append(
        Check("supabase cli", code == 0, out if code == 0 else "not found", "pnpm install")
    )
    checks.append(
        _tool(
            "gitleaks",
            ["gitleaks", "version"],
            "Install gitleaks (pre-commit falls back to a built-in pattern scan)",
            required=False,
        )
    )

    example = root / ".env.example"
    if not (root / ".env").exists():
        checks.append(Check(".env", False, "missing", "cp .env.example .env (sg bootstrap)"))
    for name in core.required_env_names(example):
        present = bool(core.env_value(name))
        checks.append(
            Check(f"env {name}", present, "set" if present else "missing", f"Set {name} in .env")
        )
    return checks


def doctor() -> None:

    result = core.Result("doctor", "doctor")
    checks = collect()
    failed = [c for c in checks if c.required and not c.ok]
    result.ok = not failed
    result.data["checks"] = [asdict(c) for c in checks]
    table = Table(title="sg doctor")
    for col in ("check", "status", "detail", "fix"):
        table.add_column(col)
    for c in checks:
        status = "[green]pass[/]" if c.ok else ("[red]FAIL[/]" if c.required else "[yellow]warn[/]")
        table.add_row(c.name, status, c.detail, "" if c.ok else c.hint)
        result.lines.append(f"- {'pass' if c.ok else 'FAIL'} {c.name}: {c.detail}")
    if not core.OPTIONS.json:
        core.console.print(table)
        core.console.print(
            f"[red]{len(failed)} required check(s) failed[/]" if failed else "[green]all good[/]"
        )
    result.finish()
