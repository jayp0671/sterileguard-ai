"""Claude Code PostToolUse hook (Edit/Write): format the changed file. Never blocks."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BIOME_EXT = {".ts", ".tsx", ".js", ".jsx", ".json", ".jsonc", ".css"}


def command_for(path: Path) -> list[str] | None:
    if path.suffix in BIOME_EXT:
        return ["pnpm", "exec", "biome", "check", "--write", "--no-errors-on-unmatched", str(path)]
    if path.suffix == ".py":
        return ["uv", "run", "ruff", "format", str(path)]
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        path = Path(payload.get("tool_input", {}).get("file_path", ""))
    except (json.JSONDecodeError, AttributeError):
        return 0
    cmd = command_for(path)
    if not cmd or not path.exists():
        return 0
    exe = shutil.which(cmd[0])
    if exe:
        subprocess.run([exe, *cmd[1:]], cwd=ROOT, capture_output=True, check=False, timeout=60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
