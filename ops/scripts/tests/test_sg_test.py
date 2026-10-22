from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sg_cli import core
from sg_cli.commands import testing

JUNIT = """<?xml version="1.0"?>
<testsuites>
  <testsuite name="a" tests="5" failures="1" errors="1" skipped="1"/>
  <testsuite name="b" tests="3" failures="0" errors="0" skipped="0"/>
</testsuites>
"""


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "AGENTS.md").write_text("x")
    (tmp_path / "ops").mkdir()
    monkeypatch.setenv("SG_ROOT", str(tmp_path))
    core.OPTIONS.dry_run = False
    return tmp_path


def test_junit_counts_sums_suites(tmp_path: Path) -> None:
    path = tmp_path / "j.xml"
    path.write_text(JUNIT)
    assert testing.junit_counts(path) == {"passed": 5, "failed": 2, "skipped": 1}


def test_junit_counts_missing_file(tmp_path: Path) -> None:
    assert testing.junit_counts(tmp_path / "none.xml") == {"passed": 0, "failed": 0, "skipped": 0}


def test_record_upserts_latest_json(root: Path) -> None:
    now = datetime(2026, 10, 21, 12, tzinfo=UTC)
    testing.record("python", {"passed": 1, "failed": 0, "skipped": 0}, 1.234, now)
    testing.record("web-web", {"passed": 2, "failed": 0, "skipped": 0}, 2.0, now)
    testing.record("python", {"passed": 3, "failed": 1, "skipped": 0}, 3.0, now)
    data = json.loads((root / "ops" / "reports" / "test" / "latest.json").read_text())
    assert [s["suite"] for s in data["suites"]] == ["python", "web-web"]
    python = data["suites"][0]
    assert python["passed"] == 3 and python["failed"] == 1 and python["duration_s"] == 3.0
    assert python["timestamp"] == "2026-10-21T12:00:00+00:00"
    assert set(python) == {
        "suite",
        "passed",
        "failed",
        "skipped",
        "duration_s",
        "timestamp",
        "commit",
    }


def test_affected_members_picks_changed_packages() -> None:
    members, everything = testing.affected_members(
        ["packages/sim/src/sg_sim/model.py", "apps/web/src/x.ts", "docs/PLAN.md"]
    )
    assert members == ["packages/sim"] and everything is False


def test_affected_members_runs_all_on_shared_config() -> None:
    members, everything = testing.affected_members(["uv.lock"])
    assert everything is True and members == list(testing.PY_MEMBERS)


def test_affected_members_none_for_docs_only() -> None:
    assert testing.affected_members(["docs/testing.md"]) == ([], False)
