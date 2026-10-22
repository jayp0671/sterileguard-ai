"""commit-msg hook: enforce conventional commits. Stdlib only."""

from __future__ import annotations

import re
import sys

PATTERN = re.compile(r"^(feat|fix|docs|chore|refactor|test|perf|ci|build)(\(.+\))?!?: .+")


def check(message: str) -> bool:
    first = message.strip().splitlines()[0] if message.strip() else ""
    return bool(PATTERN.match(first)) or first.startswith(("Merge ", "Revert "))


def main(path: str) -> int:
    with open(path, encoding="utf-8") as fh:
        message = fh.read()
    if check(message):
        return 0
    sys.stderr.write(
        "commit message must be conventional, e.g. 'feat(api): forecast endpoint [SG-15]'\n"
        "types: feat fix docs chore refactor test perf ci build\n"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
