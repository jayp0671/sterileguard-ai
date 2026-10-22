"""Claude Code Stop hook: remind (never block) to write a handoff entry."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def main() -> int:
    out = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, check=False
    ).stdout
    changed = [line[3:] for line in out.splitlines() if line.strip()]
    if changed and not any(p.endswith("ops/memory/handoff.md") for p in changed):
        print(
            "Reminder: the working tree changed but ops/memory/handoff.md did not. Run "
            '`uv run sg memory handoff --ticket SG-XX --done "..." --next "..."`.',
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
