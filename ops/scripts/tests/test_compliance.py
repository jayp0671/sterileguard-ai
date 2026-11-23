"""SG-25: sg compliance check fails on each kind of problem."""

from __future__ import annotations

import datetime as dt
import shutil
from pathlib import Path

import pytest

from sg_cli import core
from sg_cli.commands import compliance as c

ROOT = core.repo_root()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    for rel in [
        "apps/web/src/content/legal/en",
        "apps/web/public/.well-known",
        "apps/web/src/messages",
        "apps/web/src/components/compliance",
        "supabase/migrations",
    ]:
        shutil.copytree(ROOT / rel, tmp_path / rel)
    for rel in ["apps/web/src/app/layout.tsx", "apps/api/src/sg_api/routers/compliance.py"]:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, tmp_path / rel)
    return tmp_path


def all_problems(root: Path) -> list[str]:
    return (
        c.check_legal(root)
        + c.check_security_txt(root, dt.date(2026, 11, 23))
        + c.check_footer(root)
        + c.check_versions(root)
        + c.check_migrations(root)
    )


def test_repo_passes(repo: Path) -> None:
    assert all_problems(repo) == []


def test_missing_page_and_bad_version(repo: Path) -> None:
    (c.legal_dir(repo) / "cookies.md").unlink()
    terms = c.legal_dir(repo) / "terms.md"
    terms.write_text(
        terms.read_text(encoding="utf-8").replace("version: 1.0.0", "version: 1"), encoding="utf-8"
    )
    probs = all_problems(repo)
    assert "legal page missing: cookies" in probs
    assert any("terms: version" in p for p in probs)
    assert any("API asks users to accept" in p for p in probs)


def test_hipaa_claim_is_caught(repo: Path) -> None:
    p = c.legal_dir(repo) / "security.md"
    p.write_text(
        p.read_text(encoding="utf-8") + "\nThe app is HIPAA compliant.\n", encoding="utf-8"
    )
    assert any("claims HIPAA compliance" in x for x in all_problems(repo))


def test_expired_security_txt(repo: Path) -> None:
    assert c.check_security_txt(repo, dt.date(2027, 7, 1)) == [
        "security.txt: Expires is in the past"
    ]


def test_footer_removed(repo: Path) -> None:
    layout = repo / "apps/web/src/app/layout.tsx"
    layout.write_text(
        layout.read_text(encoding="utf-8").replace("<SiteFooter", "<Other"), encoding="utf-8"
    )
    assert "root layout does not render SiteFooter" in all_problems(repo)


def test_identifier_column_in_a_migration(repo: Path) -> None:
    (repo / "supabase/migrations/9999_bad.sql").write_text(
        "create table public.visits (\n  id uuid,\n  patient_mrn text\n);\n", encoding="utf-8"
    )
    assert any("patient_mrn" in p for p in all_problems(repo))


@pytest.mark.parametrize(
    ("name", "bad"),
    [
        ("patient_name", True),
        ("mrn", True),
        ("patient_dob", True),
        ("ssn_last4", True),
        ("adobe_score", False),
        ("mf_cases", False),
        ("random_number", False),
    ],
)
def test_forbidden_names(name: str, bad: bool) -> None:
    assert c.forbidden(name) is bad
