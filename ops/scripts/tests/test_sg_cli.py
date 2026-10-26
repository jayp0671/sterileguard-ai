from __future__ import annotations

import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from sg_cli import core
from sg_cli.commands import doctor, memory
from sg_cli.main import app, hoist_flags

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "ops" / "scripts" / "hooks"))

import commit_msg  # noqa: E402
import secret_scan  # noqa: E402

runner = CliRunner()


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A temporary git repo shaped like ours, with SG_ROOT pointing at it."""
    # Inside a git hook (pre-push) GIT_DIR and friends point at the real repo.
    for var in ("GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE", "GIT_PREFIX"):
        monkeypatch.delenv(var, raising=False)
    (tmp_path / "AGENTS.md").write_text("x")
    mem = tmp_path / "ops" / "memory"
    mem.mkdir(parents=True)
    (mem / "TASKS.md").write_text(
        "Current sprint: Sprint 1\n\n| ID | Title | Lead | Status | PR |\n| --- |\n"
        "| SG-01 | Repo | Jay | to do | |\n"
    )
    (mem / "handoff.md").write_text("# Handoff\n")
    (mem / "DECISIONS.md").write_text("| ADR | Title | Status |\n")
    adr = tmp_path / "docs" / "adr"
    adr.mkdir(parents=True)
    (adr / "0000-template.md").write_text("# NNNN. TITLE\n\n- Date: YYYY-MM-DD\n")
    (adr / "0001-first.md").write_text("# 0001\n")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test Agent")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "chore: init")
    monkeypatch.setenv("SG_ROOT", str(tmp_path))
    core.OPTIONS.dry_run = False
    core.OPTIONS.json = False
    return tmp_path


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("v20.19.0", (20, 19, 0)),
        ("git version 2.45.1.windows.1", (2, 45, 1)),
        ("uv 0.13", (0, 13, 0)),
    ],
)
def test_parse_version_extracts_first_version(text: str, expected: tuple[int, int, int]) -> None:
    assert core.parse_version(text) == expected


def test_parse_version_returns_none_without_digits() -> None:
    assert core.parse_version("not found") is None


def test_doctor_node_matches_major_only() -> None:
    assert doctor.node_matches("24", "v24.10.0")
    assert not doctor.node_matches("24", "v20.19.0")
    assert doctor.node_matches("lts/*", "v22.1.0")


def test_doctor_python_ok_requires_312() -> None:
    assert doctor.python_ok("Python 3.12.15")
    assert not doctor.python_ok("Python 3.10.6")


def test_required_env_names_skips_optional(tmp_path: Path) -> None:
    example = tmp_path / ".env.example"
    example.write_text("# c\nA=1\nB= # optional\n\nC=\n")
    assert core.required_env_names(example) == ["A", "C"]


def test_doctor_exits_nonzero_with_hint_when_env_missing(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (repo / ".nvmrc").write_text("24\n")
    (repo / ".env.example").write_text("SG_TEST_SURELY_MISSING=\n")
    monkeypatch.delenv("SG_TEST_SURELY_MISSING", raising=False)
    result = runner.invoke(app, ["--json", "doctor"])
    assert result.exit_code == 1
    assert "Set SG_TEST_SURELY_MISSING in .env" in result.output


def test_write_report_path_and_header(repo: Path) -> None:
    path = core.write_report("memory", "sync", "hello", now=datetime(2026, 10, 21, 9, 5, 7))
    assert path == repo / "ops" / "reports" / "memory" / "20261021-090507-sync.md"
    assert path.read_text(encoding="utf-8").startswith("# sg memory sync")


def test_memory_sync_is_idempotent(repo: Path) -> None:
    assert memory.sync_state(repo) is True
    first = (repo / "ops" / "memory" / "STATE.md").read_text(encoding="utf-8")
    assert memory.sync_state(repo) is False
    assert (repo / "ops" / "memory" / "STATE.md").read_text(encoding="utf-8") == first
    assert first.startswith(memory.STATE_HEADER)
    assert "Sprint 1" in first and "chore: init" in first


def test_adr_numbering_uses_next_number(repo: Path) -> None:
    path = memory.new_adr(repo, "Use RLS everywhere", today=date(2026, 10, 21))
    assert path.name == "0002-use-rls-everywhere.md"
    assert path.read_text(encoding="utf-8").startswith("# 0002. Use RLS everywhere")
    assert "0002" in (repo / "ops" / "memory" / "DECISIONS.md").read_text(encoding="utf-8")


def test_handoff_append_format() -> None:
    entry = memory.format_handoff(date(2026, 10, 21), "Agent", "SG-01", "built", "SG-02", "")
    assert entry == (
        "\n## 2026-10-21 · Agent · SG-01\n\n- Done: built\n- Next: SG-02\n- Gotchas: none\n"
    )


def test_handoff_command_appends(repo: Path) -> None:
    result = runner.invoke(
        app,
        ["memory", "handoff", "--ticket", "SG-01", "--done", "a", "--next", "b", "--gotchas", "c"],
    )
    assert result.exit_code == 0, result.output
    text = (repo / "ops" / "memory" / "handoff.md").read_text(encoding="utf-8")
    assert "· Test Agent · SG-01" in text and "- Next: b" in text


def test_task_mark_done() -> None:
    md = "| SG-01 | Repo | Jay | to do | |"
    assert memory.mark_done(md, "SG-01", "#1").strip() == "| SG-01 | Repo | Jay | done | #1 |"


def test_global_flags_anywhere_and_json(repo: Path) -> None:
    # Uses a command that is still a stub (sg sim run became real in SG-09, sg ml train in SG-13).
    result = runner.invoke(app, ["--json", "--dry-run", "fix", "run"])
    assert result.exit_code == 0
    assert '"ticket": "SG-30"' in result.output and '"dry_run": true' in result.output


def test_help_lists_every_group() -> None:
    result = runner.invoke(app, ["--help"])
    for group in ("doctor", "bootstrap", "dev", "memory", "db", "sim", "ml", "test", "demo"):
        assert group in result.output


def test_commit_msg_rules() -> None:
    assert commit_msg.check("feat(api): forecast endpoint [SG-15]")
    assert commit_msg.check("chore: init")
    assert not commit_msg.check("added stuff")


def test_secret_scan_blocks_fake_aws_key() -> None:
    fake = "AKIA" + "ABCDEFGHIJKLMNOP"
    assert secret_scan.scan(f"+aws_key = '{fake}'\n")
    assert not secret_scan.scan("+nothing here\n")


def test_hoist_flags_moves_global_flags_first() -> None:
    assert hoist_flags(["memory", "sync", "--json", "--dry-run"]) == [
        "--json",
        "--dry-run",
        "memory",
        "sync",
    ]


def test_redact_secrets_masks_url_passwords() -> None:
    url = "postgresql://postgres.ref:s3cr%40t@pooler.example:5432/postgres"
    assert core.redact_secrets(f"supabase db push --db-url {url}") == (
        "supabase db push --db-url postgresql://postgres.ref:***@pooler.example:5432/postgres"
    )


def test_db_url_guards_local_and_hosted(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from sg_cli.commands import db

    monkeypatch.setenv("SG_ROOT", str(tmp_path))
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://u:p@db.hosted.example:5432/postgres")
    with pytest.raises(SystemExit):
        db.db_url("local")
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://u:p@127.0.0.1:54322/postgres")
    assert db.db_url("local").endswith("127.0.0.1:54322/postgres")
    monkeypatch.setenv("SUPABASE_DB_URL_STAGING", "postgresql://u:p@127.0.0.1:54322/postgres")
    with pytest.raises(SystemExit):
        db.db_url("staging")
