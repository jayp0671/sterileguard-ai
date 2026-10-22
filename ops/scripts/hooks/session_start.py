"""Claude Code SessionStart hook: print STATE.md and the last 80 lines of handoff.md."""

from __future__ import annotations

import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MEM = ROOT / "ops" / "memory"


def main() -> int:
    state = MEM / "STATE.md"
    handoff = MEM / "handoff.md"
    out = ["# Repo memory (ops/memory)", ""]
    out.append(state.read_text(encoding="utf-8") if state.exists() else "STATE.md missing")
    if handoff.exists():
        tail = handoff.read_text(encoding="utf-8").splitlines()[-80:]
        out += ["", "## handoff.md (last 80 lines)", "", *tail]
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
