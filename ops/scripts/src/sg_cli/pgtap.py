"""Minimal pgTAP runner over psycopg, so supabase/tests run without Docker (pg_prove).

Each test file wraps itself in begin ... rollback, so running it against staging leaves no trace.
Statements run one at a time (split with sqlparse, which understands dollar quoting) and every
TAP line a statement returns is collected.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import psycopg
import sqlparse

TAP_RE = re.compile(r"^(not ok|ok)\b")
PLAN_RE = re.compile(r"^1\.\.(\d+)")


@dataclass
class FileResult:
    name: str
    lines: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def passed(self) -> int:
        return sum(1 for line in self.lines if line.startswith("ok"))

    @property
    def failed(self) -> int:
        return sum(1 for line in self.lines if line.startswith("not ok"))

    @property
    def planned(self) -> int | None:
        for line in self.lines:
            if m := PLAN_RE.match(line):
                return int(m.group(1))
        return None

    @property
    def ok(self) -> bool:
        ran = self.passed + self.failed
        return self.error is None and self.failed == 0 and self.planned in (None, ran)


def tap_lines(rows: list[tuple[object, ...]]) -> list[str]:
    out: list[str] = []
    for row in rows:
        if len(row) != 1 or not isinstance(row[0], str):
            continue
        for line in row[0].splitlines():
            if TAP_RE.match(line) or PLAN_RE.match(line) or line.startswith("#"):
                out.append(line)
    return out


def run_file(conninfo: str, path: Path) -> FileResult:
    result = FileResult(path.name)
    statements = [s for s in sqlparse.split(path.read_text(encoding="utf-8")) if s.strip()]
    with psycopg.connect(conninfo, autocommit=True, connect_timeout=15) as conn:
        try:
            for stmt in statements:
                cur = conn.execute(stmt.encode("utf-8"))
                if cur.description:
                    result.lines += tap_lines(list(cur.fetchall()))
        except psycopg.Error as exc:
            result.error = f"{type(exc).__name__}: {str(exc).splitlines()[0]}"
            conn.execute("rollback")
    return result


def run_dir(conninfo: str, folder: Path) -> list[FileResult]:
    return [run_file(conninfo, p) for p in sorted(folder.glob("*.test.sql"))]
