"""SG-21: import pipeline v1 and the PHI guard. Every file here is synthetic, built in memory;
the fake names, phone numbers and IDs are invented."""

from __future__ import annotations

import datetime as dt
import io
import logging
from pathlib import Path

import pandas as pd
import pytest
from openpyxl import Workbook

from sg_data import phi
from sg_data.imports import run
from sg_data.imports.commit import InMemoryBackend, commit
from sg_data.imports.mapping import normalize, propose, signature
from sg_data.imports.parse import ParseError, parse_bytes
from sg_data.imports.transform import (
    normalize_shift,
    parse_bool,
    parse_date,
    parse_duration,
    parse_time_minutes,
)

DEPT = "00000000-0000-4000-8000-000000000003"
TEMPLATE = Path(__file__).resolve().parents[3] / "docs" / "domain" / "daily-log-template.csv"
FAKE = {"name": "Jordan Testcase", "phone": "201-555-0199", "email": "j.testcase@example.test"}


def week1_like() -> bytes:
    """Same columns as the daily log template (what Leo's week 1 uses), synthetic values."""
    header = TEMPLATE.read_text(encoding="utf-8").splitlines()[0]
    rows = [
        "2026-09-14,380,3,10.5,21,4,3,1,2,2,2,2,2,0,false,none,12,140,0,",
        "2026-09-15,355,3,8.0,18,3,3,1,2,2,2,2,2,1,false,none,9,120,30,washer 2 slow",
        "2026-09-16,430,3,14.25,24,5,3,1,2,2,2,2,1,1,false,none,15,210,45,",
        "2026-09-17,401,3,11.0,19,4,3,1,2,2,2,2,2,2,false,none,11,160,0,",
        "2026-09-18,262,3,3.5,15,2,3,1,2,2,2,2,2,0,false,none,6,80,0,",
    ]
    return ("\n".join([header, *rows]) + "\n").encode()


def xlsx(rows: list[list[object]], merges: list[str] = (), sheets: int = 1) -> bytes:  # type: ignore[assignment]
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Log"
    for r in rows:
        ws.append(r)
    for m in merges:
        ws.merge_cells(m)
    for i in range(1, sheets):
        wb.create_sheet(f"Notes {i}").append(["just a note"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# --- acceptance: week 1 imports with mapping confirmations only ----------------------------


def test_week1_structure_maps_and_validates_without_cleanup() -> None:
    res = run(week1_like(), "week1.csv")
    assert all(m.field == m.column and m.method == "exact" for m in res.mapping)
    assert res.errors == []
    assert res.valid_rows == 5
    assert res.valid["regular_patients"].tolist() == [380, 355, 430, 401, 262]
    assert res.valid["ot_labor_hours"].tolist() == [10.5, 8.0, 14.25, 11.0, 3.5]


def test_commit_creates_lineage_and_is_idempotent() -> None:
    res = run(week1_like(), "week1.csv")
    backend = InMemoryBackend()
    kw = dict(department_id=DEPT, settings={}, content_hash=res.content_hash, filename="w.csv")
    first = commit(backend, res.valid, import_job_id="job-1", **kw)  # type: ignore[arg-type]
    assert (first.plans, first.actuals) == (5, 5)
    dataset = backend.datasets[0]
    assert dataset["import_job_id"] == "job-1" and dataset["source"] == "real"
    assert dataset["content_hash"] == res.content_hash
    plan = backend.plans[(DEPT, dt.date(2026, 9, 14))]
    assert plan["source"] == "real" and plan["dataset_id"] == dataset["id"]
    actual = backend.actuals[(DEPT, dt.date(2026, 9, 14))]
    assert actual["ot_labor_hours"] == 10.5 and actual["dataset_id"] == dataset["id"]

    again = commit(backend, res.valid, import_job_id="job-2", **kw)  # type: ignore[arg-type]
    assert again.already_committed and again.rows_committed == 0
    assert len(backend.datasets) == 1 and len(backend.plans) == 5


def test_existing_days_are_skipped_unless_overwrite() -> None:
    res = run(week1_like(), "week1.csv")
    backend = InMemoryBackend()
    backend.plans[(DEPT, dt.date(2026, 9, 15))] = {"plan_date": dt.date(2026, 9, 15)}
    out = commit(
        backend,
        res.valid,
        department_id=DEPT,
        settings={},
        import_job_id="j",
        content_hash="h",
        filename="f",
    )
    assert out.skipped_dates == ["2026-09-15"] and out.plans == 4


# --- PHI ----------------------------------------------------------------------------------


def phi_file() -> bytes:
    return (
        "Date,Employee,Badge #,Patients,Staff,OT hrs,Notes\n"
        f"10/12/26,{FAKE['name']},48213,392,3,4.5,call {FAKE['phone']} if late\n"
        f"10/13/26,{FAKE['name']},48213,343,3,2.0,fine\n"
        f"10/14/26,{FAKE['name']},48213,442,3,6.0,emailed {FAKE['email']}\n"
    ).encode()


def test_identity_columns_are_dropped_and_phi_cells_blocked(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    res = run(phi_file(), "phi.csv")
    assert set(res.dropped_columns) == {"Employee", "Badge #"}
    assert {"entity_type": "IDENTITY_COLUMN", "column": "Employee", "row": None} in res.phi_findings
    cells = {(f["entity_type"], f["row"]) for f in res.phi_findings if f["row"] is not None}
    assert cells == {("PHONE_NUMBER", 0), ("EMAIL_ADDRESS", 2)}
    assert res.blocked_rows == [0, 2]
    text = str(res.report()) + res.valid.to_csv() + caplog.text
    for value in [*FAKE.values(), "48213"]:
        assert value not in text
    # The other columns of the blocked rows still import; only the cell was cleared.
    assert res.valid_rows == 3
    notes = res.valid["notes"].tolist()
    assert notes[1] == "fine" and pd.isna(notes[0]) and pd.isna(notes[2])


def test_profile_records_no_samples_for_flagged_columns() -> None:
    res = run(phi_file(), "phi.csv")
    notes = next(c for c in res.profile if c["column"] == "Notes")
    assert notes["phi"] is True and notes["samples"] == []
    patients = next(c for c in res.profile if c["column"] == "Patients")
    assert patients["dtype"] == "number" and patients["min"] == 343


def test_counts_are_never_scanned_as_phi() -> None:
    df = pd.DataFrame({"Patients": ["392", "8005550123"], "Employees": [3, 4]})
    out = phi.scan_frame(df)
    assert out.findings == [] and list(out.frame.columns) == ["Patients", "Employees"]


@pytest.mark.parametrize(
    ("header", "values", "identity"),
    [
        ("Employee", ["A B", "C D"], True),
        ("Employees", ["3", "4"], False),
        ("Patient Name", None, True),
        ("Regular patients", ["300"], False),
        ("MRN", ["123456"], True),
        ("Staff ID", ["12"], True),
        ("DOB", None, True),
        ("Notes", ["x"], False),
    ],
)
def test_identity_headers(header: str, values: list[str] | None, identity: bool) -> None:
    series = pd.Series(values) if values is not None else None
    assert phi.is_identity_column(header, series) is identity


def test_guard_text_reports_types_only() -> None:
    assert phi.guard_text("Washer 2 down after lunch, 392 patients").ok
    res = phi.guard_text(f"ask {FAKE['name']} at {FAKE['email']}")
    assert not res.ok and set(res.entity_types) == {"PERSON", "EMAIL_ADDRESS"}
    assert phi.guard_text("DOB 04/12/1980").entity_types == ["DATE_OF_BIRTH"]
    assert phi.guard_text("Dr. Okafor's clinic ran late").entity_types == ["PERSON"]


# --- row-level validation errors ----------------------------------------------------------


def test_validation_errors_point_at_file_rows() -> None:
    data = (
        b"date,regular_patients,morning_staff_present,ot_labor_hours\n"
        b"2026-10-12,392,3,4.5\n"
        b"2026-10-13,-5,3,2\n"
        b"2026-10-14,400,three,2\n"
        b"2026-10-12,380,3,1\n"
    )
    res = run(data, "e.csv")
    by_row = {e["row"]: e for e in res.errors}
    assert by_row[1]["column"] == "regular_patients"
    assert by_row[2]["column"] == "morning_staff_present"
    assert "earlier in the file" in by_row[3]["message"]
    assert res.valid_rows == 1


def test_missing_required_column_is_a_file_error() -> None:
    res = run(b"date,ot_labor_hours\n2026-10-12,3\n", "m.csv")
    assert any(e["row"] is None and e["column"] == "regular_patients" for e in res.errors)
    assert res.valid_rows == 0


# --- parsing --------------------------------------------------------------------------------


def test_two_row_header_merged_cells_total_row_and_largest_sheet() -> None:
    rows: list[list[object]] = [
        ["Daily log", None, None, None],
        [None, None, None, None],
        ["Shift", "Patients", "Staff", "Overtime"],
        ["Date", "Regular", "Morning", "Hours"],
        [dt.datetime(2026, 10, 12), 392, 3, "4h30"],
        [dt.datetime(2026, 10, 13), 343, 3, "2:15"],
        ["Total", 735, None, None],
    ]
    data = xlsx(rows, merges=["A1:D1"], sheets=3)
    df, report = parse_bytes(data, "log.xlsx")
    assert report.sheet == "Log" and len(report.sheets) == 3
    # Positions after empty rows are dropped (the blank second row is gone).
    assert report.header_rows == [1, 2] and report.dropped_total_row
    assert list(df.columns) == ["Shift Date", "Patients Regular", "Staff Morning", "Overtime Hours"]
    res = run(data, "log.xlsx")
    assert [m.field for m in res.mapping] == [
        "date",
        "regular_patients",
        "morning_staff_present",
        "ot_labor_hours",
    ]
    assert res.valid["ot_labor_hours"].tolist() == [4.5, 2.25]


def test_semicolon_latin1_csv() -> None:
    text = "Datum;Patients;Staff present;Overtime;Notes\n12/10/2026;392;3;4,5;café ok\n"
    df, report = parse_bytes(text.encode("latin-1"), "eu.csv")
    assert report.delimiter == ";" and report.encoding is not None
    assert df.iloc[0]["Notes"] == "café ok"


def test_rejects_wrong_type_and_large_files() -> None:
    with pytest.raises(ParseError, match="unsupported"):
        parse_bytes(b"x", "a.pdf")
    with pytest.raises(ParseError, match="10 MB"):
        parse_bytes(b"a" * (10 * 1024 * 1024 + 1), "a.csv")


def test_wide_files_with_days_as_columns() -> None:
    data = (
        b"Measure,10/12/2026,10/13/2026,10/14/2026\n"
        b"Patients,392,343,442\n"
        b"Staff present,3,3,3\n"
        b"OT hours,4.5,2,6\n"
    )
    res = run(data, "wide.csv")
    assert res.wide and res.valid_rows == 3
    assert res.valid["date"].tolist() == [dt.date(2026, 10, d) for d in (12, 13, 14)]


def test_punch_out_times_aggregate_to_daily_overtime() -> None:
    data = (
        "Date,Employee,Clock out,Patients,Staff\n"
        f"10/12/26,{FAKE['name']},20:00,392,3\n"
        "10/12/26,Avery Sample,19:30,392,3\n"
        "10/12/26,Riley Example,18:00,392,3\n"
        f"10/13/26,{FAKE['name']},3:00 PM,343,3\n"
    ).encode()
    res = run(data, "punch.csv")
    assert "Employee" in res.dropped_columns
    assert res.valid["ot_labor_hours"].tolist() == [12.5, 0.0]
    assert any("aggregated" in n for n in res.transform_notes)
    assert "Avery Sample" not in str(res.report()) + res.valid.to_csv()


def test_morning_shift_rows_only() -> None:
    data = (
        b"Date,Shift,Patients,Staff,OT\n"
        b"10/12/26,AM,392,3,4\n10/12/26,PM,100,2,1\n10/13/26,7-3,343,3,2\n"
    )
    res = run(data, "shifts.csv")
    assert res.valid_rows == 2


# --- mapping and transforms ---------------------------------------------------------------


def test_mapping_methods_and_templates() -> None:
    headers = ["Shift date", "Pts", "AM staff", "Overtim hours (h)", "Weather"]
    proposal = {m.column: (m.field, m.method) for m in propose(headers)}
    assert proposal["Shift date"] == ("date", "synonym")
    assert proposal["Pts"] == ("regular_patients", "synonym")
    assert proposal["Overtim hours (h)"][0] == "ot_labor_hours"
    assert proposal["Weather"] == (None, None)
    sig = signature(headers)
    saved = {sig: {"Weather": "notes", "Pts": "regular_patients"}}
    templated = {m.column: (m.field, m.method) for m in propose(headers, saved)}
    assert templated["Weather"] == ("notes", "template")
    assert signature(list(reversed(headers))) == sig
    assert normalize("OT Hours (decimal)") == "ot hours"


@pytest.mark.parametrize(
    ("raw", "hours"),
    [("3h30", 3.5), ("3:30", 3.5), ("3.5", 3.5), ("210 min", 3.5), ("3 hrs", 3.0), (2, 2.0)],
)
def test_durations(raw: object, hours: float) -> None:
    assert parse_duration(raw) == pytest.approx(hours)


def test_dates_booleans_times_and_shift_labels() -> None:
    assert parse_date("10/12/26") == dt.date(2026, 10, 12)
    assert parse_date("Oct 12") == dt.date(2026, 10, 12)
    assert parse_date(46307) == dt.date(2026, 10, 12)
    assert parse_date("2026-10-12") == dt.date(2026, 10, 12)
    assert [parse_bool(v) for v in ("y", "Yes", "x", "1", "no")] == [True, True, True, True, False]
    assert parse_time_minutes("7:30 PM") == 19 * 60 + 30
    assert [normalize_shift(s) for s in ("AM", "7-3", "morning", "day", "PM")] == [
        "morning",
        "morning",
        "morning",
        "morning",
        "evening",
    ]
