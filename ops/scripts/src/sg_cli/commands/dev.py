"""sg dev: ensure Supabase is up, then run web and API with prefixed, colored output."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from typing import IO

import typer
from rich.markup import escape

from sg_cli import core

PROCS: list[tuple[str, str, list[str]]] = [
    ("web", "magenta", ["pnpm", "--filter", "@sg/web", "dev"]),
    (
        "api",
        "cyan",
        [
            "uv",
            "run",
            "uvicorn",
            "sg_api.main:create_app",
            "--factory",
            "--reload",
            "--port",
            "8000",
            "--app-dir",
            "apps/api/src",
        ],
    ),
]


def _pump(name: str, color: str, stream: IO[str]) -> None:
    # Child output may contain characters the console encoding (cp1252 on Windows) lacks.
    encoding = sys.stdout.encoding or "utf-8"
    for line in stream:
        safe = line.rstrip().encode(encoding, "replace").decode(encoding)
        core.console.print(f"[{color}]{name:>4} |[/] {escape(safe)}", markup=True, soft_wrap=True)


def dev(
    no_db: bool = typer.Option(False, "--no-db", help="Skip local Supabase (use .env URLs)."),
) -> None:
    result = core.Result("dev", "dev")
    if not no_db:
        code, _ = core.capture(["pnpm", "exec", "supabase", "status"])
        if code != 0:
            docker, _ = core.capture(["docker", "info"])
            if docker == 0:
                result.add("starting local Supabase")
                core.run(["pnpm", "exec", "supabase", "start"])
            else:
                result.add("Docker not running: continuing without local Supabase")
    for name, _, cmd in PROCS:
        result.add(f"{name}: {' '.join(cmd)}")
    if core.OPTIONS.dry_run:
        result.finish()
        return

    procs: list[subprocess.Popen[str]] = []
    threads: list[threading.Thread] = []
    try:
        for name, color, cmd in PROCS:
            proc = subprocess.Popen(
                [core.which(cmd[0]) or cmd[0], *cmd[1:]],
                cwd=core.repo_root(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env={**os.environ, "FORCE_COLOR": "1"},
            )
            procs.append(proc)
            assert proc.stdout is not None
            t = threading.Thread(target=_pump, args=(name, color, proc.stdout), daemon=True)
            t.start()
            threads.append(t)
        for proc in procs:
            proc.wait()
    except KeyboardInterrupt:
        core.console.print("stopping...")
    finally:
        for proc in procs:
            if proc.poll() is None:
                proc.terminate()
        for proc in procs:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        result.finish()
