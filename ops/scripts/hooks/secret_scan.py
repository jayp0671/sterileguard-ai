"""pre-commit secret scan. Runs gitleaks when installed; otherwise a built-in pattern scan of the
staged diff so the hook still blocks obvious secrets on machines without gitleaks. Stdlib only."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys

PATTERNS = {
    "AWS access key": re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b"),
    "private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    "Slack token": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"),
    "Supabase secret key": re.compile(r"\bsb_secret_[A-Za-z0-9_-]{20,}\b"),
    "NVIDIA API key": re.compile(r"\bnvapi-[A-Za-z0-9_-]{20,}\b"),
    "JWT": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
}
ALLOW_MARKER = "gitleaks:allow"


def scan(diff: str) -> list[str]:
    hits = []
    for line in diff.splitlines():
        if not line.startswith("+") or line.startswith("+++") or ALLOW_MARKER in line:
            continue
        for name, pattern in PATTERNS.items():
            if pattern.search(line):
                hits.append(f"{name}: {line[:80]}")
    return hits


def main() -> int:
    if shutil.which("gitleaks"):
        return subprocess.call(["gitleaks", "protect", "--staged", "--redact", "-v"])
    diff = subprocess.run(
        ["git", "diff", "--cached", "-U0"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    ).stdout
    hits = scan(diff)
    if hits:
        sys.stderr.write("possible secret in staged changes (install gitleaks for full scan):\n")
        sys.stderr.write("\n".join(f"  {h}" for h in hits) + "\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
