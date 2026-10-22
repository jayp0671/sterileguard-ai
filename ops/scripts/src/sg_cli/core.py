"""Shared helpers for every sg command: options, process running, reports, env."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console

console = Console(highlight=False)


class CommandError(RuntimeError):
    """A subprocess exited non-zero."""

    def __init__(self, cmd: Sequence[str], returncode: int) -> None:
        super().__init__(f"command failed ({returncode}): {redact_secrets(' '.join(cmd))}")
        self.cmd = list(cmd)
        self.returncode = returncode


@dataclass
class Options:
    dry_run: bool = False
    json: bool = False


OPTIONS = Options()


def repo_root() -> Path:
    """Repo root: SG_ROOT if set, else the nearest parent holding AGENTS.md and ops/."""
    env = os.environ.get("SG_ROOT")
    if env:
        return Path(env).resolve()
    here = Path.cwd().resolve()
    for candidate in (here, *here.parents):
        if (candidate / "AGENTS.md").exists() and (candidate / "ops").is_dir():
            return candidate
    return Path(__file__).resolve().parents[4]


def which(name: str) -> str | None:
    """Locate an executable, including Windows .cmd shims (pnpm, npx)."""
    import shutil

    return shutil.which(name)


_CRED_RE = re.compile(r"(://[^:/@\s]+:)[^@\s]+@")


def redact_secrets(text: str) -> str:
    """Mask passwords in URLs (postgres://user:pass@host) before printing or reporting."""
    return _CRED_RE.sub(lambda m: m.group(1) + "***@", text)


def run(
    cmd: Sequence[str],
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
    check: bool = True,
) -> int:
    """Run a command with streamed output. Honors --dry-run. Raises CommandError on failure."""
    printable = redact_secrets(" ".join(cmd))
    if OPTIONS.dry_run:
        console.print(f"[dim]would run:[/] {printable}")
        return 0
    console.print(f"[cyan]$[/] {printable}")
    merged = {**os.environ, **(env or {})}
    exe = which(cmd[0]) or cmd[0]
    proc = subprocess.run([exe, *cmd[1:]], cwd=cwd or repo_root(), env=merged, check=False)
    if check and proc.returncode != 0:
        raise CommandError(cmd, proc.returncode)
    return proc.returncode


def capture(cmd: Sequence[str], cwd: Path | None = None) -> tuple[int, str]:
    """Run a command and capture combined output. Never raises for a missing binary."""
    exe = which(cmd[0])
    if exe is None:
        return 127, f"{cmd[0]}: not found"
    try:
        proc = subprocess.run(
            [exe, *cmd[1:]],
            cwd=cwd or repo_root(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=60,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return 127, str(exc)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


VERSION_RE = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")


def parse_version(text: str) -> tuple[int, int, int] | None:
    """Extract the first version from tool output, e.g. 'v20.19.0' -> (20, 19, 0)."""
    match = VERSION_RE.search(text)
    if not match:
        return None
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch or 0)


def read_env_file(path: Path) -> dict[str, str]:
    """Parse a dotenv file (KEY=value lines, # comments)."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.split(" #")[0].strip().strip('"').strip("'")
    return values


def required_env_names(example: Path) -> list[str]:
    """Names in .env.example, skipping any line tagged '# optional'."""
    names: list[str] = []
    if not example.exists():
        return names
    for raw in example.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line or "# optional" in line:
            continue
        names.append(line.split("=", 1)[0].strip())
    return names


def env_value(name: str) -> str | None:
    """A variable from the process environment, falling back to the repo .env file."""
    return os.environ.get(name) or read_env_file(repo_root() / ".env").get(name) or None


def require_env(*names: str) -> dict[str, str]:
    """Return the requested variables; exit listing any that are missing."""
    found = {name: env_value(name) for name in names}
    missing = [name for name, value in found.items() if not value]
    if missing:
        raise SystemExit(f"missing env vars: {', '.join(missing)} (add them to .env)")
    return {k: v for k, v in found.items() if v}


def write_report(group: str, name: str, body: str, now: datetime | None = None) -> Path:
    """Write ops/reports/<group>/<YYYYMMDD-HHMMSS>-<name>.md and return its path."""
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    folder = repo_root() / "ops" / "reports" / group
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{stamp}-{name}.md"
    header = f"# sg {group} {name}\n\n_{stamp} · dry_run={OPTIONS.dry_run}_\n\n"
    path.write_text(header + body.rstrip() + "\n", encoding="utf-8")
    return path


@dataclass
class Result:
    """Collects a command's outcome, prints it as text or JSON, and writes the report."""

    group: str
    name: str
    ok: bool = True
    lines: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)

    def add(self, line: str) -> None:
        self.lines.append(line)
        if not OPTIONS.json:
            console.print(line)

    def finish(self) -> None:
        report = write_report(self.group, self.name, "\n".join(self.lines) or "(no output)")
        if OPTIONS.json:
            payload = {"command": f"{self.group} {self.name}", "ok": self.ok, **self.data}
            payload["dry_run"] = OPTIONS.dry_run
            payload["report"] = str(report)
            sys.stdout.write(json.dumps(payload, indent=2, default=str) + "\n")
        if not self.ok:
            raise SystemExit(1)
