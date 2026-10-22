"""sg bootstrap: install dependencies, create .env, start local Supabase, reset the db."""

from __future__ import annotations

import shutil

from sg_cli import core


def bootstrap() -> None:
    result = core.Result("bootstrap", "bootstrap")
    root = core.repo_root()
    steps: list[tuple[str, list[str]]] = [
        ("install node packages", ["pnpm", "install"]),
        ("install python packages", ["uv", "sync", "--all-packages"]),
    ]
    for label, cmd in steps:
        result.add(f"- {label}")
        core.run(cmd)

    env, example = root / ".env", root / ".env.example"
    if env.exists():
        result.add("- .env exists, left unchanged")
    else:
        result.add("- copy .env.example to .env")
        if not core.OPTIONS.dry_run:
            shutil.copyfile(example, env)

    docker_up, _ = core.capture(["docker", "info"])
    if docker_up == 0:
        result.add("- start local Supabase and reset the database")
        core.run(["pnpm", "exec", "supabase", "start"])
        core.run(["uv", "run", "sg", "db", "reset"])
    else:
        result.add("- Docker is not running: skipped local Supabase (start Docker, rerun)")

    result.add("- install git hooks")
    core.run(["pnpm", "exec", "lefthook", "install"])
    result.add("done. Next: sg doctor, then sg dev")
    result.finish()
