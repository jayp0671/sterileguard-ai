"""SG-08 canonical schema tests. Synthetic rows only."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import pandas as pd
import pandera.errors as pae
import pytest
from pydantic import ValidationError

from sg_data import schema
from sg_data.defaults import fill_tier2, resolve_setting

DEPT = "00000000-0000-4000-8000-000000000003"
SETTINGS: dict[str, Any] = {
    "shift_windows": [
        {"key": "aft_11", "default_staff": 3},
        {"key": "aft_13", "default_staff": 1},
        {"key": "aft_15", "default_staff": 2},
    ],
    "outside_support_default": 2,
    "washers": 2,
    "sterilizers": 2,
    "mf_cases_default": 20,
}


def valid_row(**over: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "department_id": DEPT,
        "source": "simulated",
        "dataset_id": None,
        "created_by": None,
        "date": "2026-10-20",
        "regular_patients": 310,
        "morning_staff_present": 4,
        "ot_labor_hours": 6.5,
        "mf_cases": 18,
        "student_clinic_sessions": 6,
        "aft_11_staff": 3,
        "aft_13_staff": 1,
        "aft_15_staff": 2,
        "outside_support_staff": 2,
        "ot_available_staff": 3,
        "washers_up": 2,
        "sterilizers_up": 2,
        "carryover_backlog_estimate": 1,
        "is_holiday": False,
        "academic_event": "none",
        "emergency_intake_patients": 12,
        "returned_unused_estimate": 40,
        "equipment_downtime_minutes": 0,
        "notes": "",
    }
    row.update(over)
    return row


def frame(*rows: dict[str, Any]) -> pd.DataFrame:
    return pd.DataFrame(list(rows))


def test_valid_row_passes() -> None:
    schema.to_pandera().validate(frame(valid_row()), lazy=True)


@pytest.mark.parametrize(
    ("name", "bad"),
    [
        ("regular_patients", 801),
        ("regular_patients", -1),
        ("mf_cases", 81),
        ("student_clinic_sessions", 41),
        ("morning_staff_present", 21),
        ("ot_labor_hours", 60.5),
        ("equipment_downtime_minutes", 901),
        ("carryover_backlog_estimate", 3),
        ("academic_event", "party"),
    ],
)
def test_range_violation_names_the_field(name: str, bad: Any) -> None:
    with pytest.raises(pae.SchemaErrors) as err:
        schema.to_pandera().validate(frame(valid_row(**{name: bad})), lazy=True)
    assert name in str(err.value)


def test_settings_tighten_equipment_max() -> None:
    with pytest.raises(pae.SchemaErrors, match="washers_up"):
        schema.to_pandera(settings={"washers": 1}).validate(
            frame(valid_row(washers_up=2)), lazy=True
        )


@pytest.mark.parametrize("name", ["regular_patients", "morning_staff_present", "ot_labor_hours"])
def test_missing_tier1_fails(name: str) -> None:
    with pytest.raises(pae.SchemaErrors):
        schema.to_pandera().validate(frame(valid_row(**{name: None})), lazy=True)
    df = frame(valid_row()).drop(columns=[name])
    with pytest.raises(pae.SchemaErrors):
        schema.to_pandera().validate(df, lazy=True)


def test_missing_tier2_allowed() -> None:
    schema.to_pandera().validate(frame(valid_row(mf_cases=None)), lazy=True)


def test_cross_field_ot_available() -> None:
    with pytest.raises(pae.SchemaErrors, match="ot_available_staff"):
        schema.to_pandera().validate(
            frame(valid_row(ot_available_staff=5, morning_staff_present=4)), lazy=True
        )
    plan = schema.to_pydantic("plan_in")
    payload = {k: v for k, v in valid_row().items() if k in schema.INPUT_FIELDS and k != "date"}
    plan(**payload)
    with pytest.raises(ValidationError, match="ot_available_staff"):
        plan(**{**payload, "ot_available_staff": 5})


def test_unique_real_rows() -> None:
    real = valid_row(source="real")
    with pytest.raises(pae.SchemaErrors, match="duplicate real row"):
        schema.to_pandera().validate(frame(real, real), lazy=True)
    sim = valid_row()
    schema.to_pandera().validate(frame(sim, sim), lazy=True)


def test_pydantic_models_carry_ranges() -> None:
    plan = schema.to_pydantic("plan_in")
    js = plan.model_json_schema()
    rp = js["properties"]["regular_patients"]
    assert rp["minimum"] == 0
    assert rp["maximum"] == 800
    assert rp["description"]
    assert "regular_patients" in js["required"]
    assert "mf_cases" not in js.get("required", [])
    with pytest.raises(ValidationError, match="regular_patients"):
        plan(regular_patients=900, morning_staff_present=3)
    actual = schema.to_pydantic("actual_in")
    assert set(actual.model_fields) == set(schema.OUTCOME_FIELDS)
    actual(ot_labor_hours=3.0)
    row = schema.to_pydantic("row")
    assert set(row.model_fields) == {f.name for f in schema.FIELDS}
    assert schema.to_pydantic("plan_in") is plan


def test_synonyms_unique_across_fields() -> None:
    seen: dict[str, str] = {}
    for f in schema.FIELDS:
        for s in (f.name, *f.synonyms):
            key = s.lower().strip()
            assert key not in seen or seen[key] == f.name, f"{s!r} used by {seen.get(key)}"
            seen[key] = f.name


def test_template_columns_match_schema() -> None:
    root = Path(__file__).resolve().parents[3]
    header = (root / "docs/domain/daily-log-template.csv").read_text().splitlines()[0]
    non_meta = [f.name for f in schema.FIELDS if f.role != "meta"]
    assert set(header.split(",")) == set(non_meta)


def test_fill_tier2_flags_and_preserves() -> None:
    df = frame(valid_row(mf_cases=None, aft_13_staff=None), valid_row(washers_up=1))
    df = df.drop(columns=["student_clinic_sessions"])
    out = fill_tier2(df, SETTINGS)
    assert out.loc[0, "mf_cases"] == 20
    assert out.loc[0, "mf_cases__missing"]
    assert out.loc[0, "aft_13_staff"] == 1
    assert not out.loc[1, "mf_cases__missing"]
    assert out.loc[1, "mf_cases"] == 18
    assert out.loc[1, "washers_up"] == 1
    assert out["student_clinic_sessions__missing"].all()
    assert out.loc[0, "student_clinic_sessions"] == 0  # fallback when settings lack the key
    for name in schema.TIER2_INPUTS:
        assert f"{name}__missing" in out.columns


def test_fill_tier2_never_fills_tier1_or_outcomes() -> None:
    df = frame(valid_row(regular_patients=None, ot_labor_hours=None))
    out = fill_tier2(df, SETTINGS)
    assert pd.isna(out.loc[0, "regular_patients"])
    assert pd.isna(out.loc[0, "ot_labor_hours"])
    assert "regular_patients__missing" not in out.columns
    from sg_data.defaults import default_for

    with pytest.raises(ValueError, match="never auto-filled"):
        default_for("regular_patients", SETTINGS)


def test_resolve_setting() -> None:
    assert resolve_setting(SETTINGS, "shift_windows.aft_11.default_staff") == 3
    assert resolve_setting(SETTINGS, "shift_windows.nope.default_staff") is None
    assert resolve_setting(SETTINGS, "missing.path") is None


def test_db_columns_cover_schema() -> None:
    plans = schema.db_columns("shift_plans")
    assert plans["plan_date"] == "date"
    assert plans["mf_cases__missing"] == "boolean"
    assert "ot_labor_hours" not in plans
    actuals = schema.db_columns("shift_actuals")
    assert actuals["ot_labor_hours"] == "numeric"
    assert "regular_patients" not in actuals


# Files allowed to list field names: the schema itself, generated code, data templates, docs,
# SQL migrations (DDL must name columns), tests, and translation catalogs (driver sentences are
# keyed drivers.<feature>; packages/ml/tests/test_explain.py keeps en.json equal to the
# templates generated from the feature registry).
ALLOWED = re.compile(
    r"(sg_data/schema\.py|/generated/|db\.ts$|openapi\.json$|\.sql$|\.md$|\.csv$|/tests?/|"
    r"test_[^/]*\.py$|\.test\.tsx?$|\.spec\.ts$|/messages/[a-z-]+\.json$)"
)
SCAN_EXT = {".py", ".ts", ".tsx", ".js", ".yaml", ".yml", ".json"}
SKIP_DIRS = {
    "node_modules",
    ".venv",
    ".git",
    ".next",
    "dist",
    "build",
    ".turbo",
    ".claude",
    ".agents",
    "__pycache__",
    "coverage",
    "ops",
    # Gitignored datasets and training runs (their metrics.json lists the model features).
    "data",
}


def test_no_duplicated_field_lists() -> None:
    root = Path(__file__).resolve().parents[3]
    pattern = re.compile(
        r"[\"'](" + "|".join(re.escape(n) for n in schema.INPUT_FIELDS) + r")[\"']"
    )
    offenders = []
    paths: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        paths.extend(Path(dirpath) / f for f in filenames)
    for path in paths:
        if path.suffix not in SCAN_EXT:
            continue
        rel = path.relative_to(root).as_posix()
        if ALLOWED.search(rel):
            continue
        hits = set(pattern.findall(path.read_text(encoding="utf-8", errors="ignore")))
        if len(hits) >= 6:
            offenders.append(f"{rel}: {sorted(hits)}")
    assert not offenders, "field lists must come from sg_data.schema:\n" + "\n".join(offenders)
