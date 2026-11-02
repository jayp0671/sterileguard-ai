"""Deliberately messy synthetic log files for the import tests (SG-22, plan §10.3).

`sg data synth-messy --out packages/data/tests/fixtures/messy/ --seed 7` writes one file per
case plus `<file>.expected.json`. Expectations are built alongside the data (never by running
the pipeline): the mapping, the valid row count, the error rows, the PHI findings and the
values that must come out. Fake names, phones and emails come from Faker; nothing is real.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import random
import re
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sg_data.schema import BY_NAME

START = dt.date(2026, 10, 12)  # a Monday
DATE = next(f.name for f in BY_NAME.values() if f.dtype == "date")
PATIENTS = "regular_patients"
STAFF = "morning_staff_present"
OT = next(f.name for f in BY_NAME.values() if f.role == "outcome" and f.tier == 1)
MF = "mf_cases"
NOTES = "notes"
SESSIONS = "student_clinic_sessions"


@dataclass
class Day:
    date: dt.date
    patients: int
    staff: int
    ot: float
    mf: int
    sessions: int


@dataclass
class Case:
    name: str
    kind: str  # "exact" (names, synonyms) or "messy" (abbreviations, typos, layouts)
    data: bytes
    mapping: dict[str, str | None]
    rows: list[dict[str, Any]]
    error_rows: list[int] = field(default_factory=list)
    dropped_columns: list[str] = field(default_factory=list)
    phi_cells: list[dict[str, Any]] = field(default_factory=list)
    fake_strings: list[str] = field(default_factory=list)
    options: dict[str, Any] = field(default_factory=dict)

    def expected(self) -> dict[str, Any]:
        return {
            "file": self.name,
            "kind": self.kind,
            "options": self.options,
            "mapping": self.mapping,
            "valid_rows": len(self.rows),
            "rows": self.rows,
            "error_rows": self.error_rows,
            "dropped_columns": self.dropped_columns,
            "phi_cells": self.phi_cells,
            "fake_strings": self.fake_strings,
        }


class Gen:
    def __init__(self, seed: int) -> None:
        from faker import Faker

        self.rng = random.Random(seed)
        self.fake = Faker("en_US")
        self.fake.seed_instance(seed)

    def days(self, n: int = 6) -> list[Day]:
        out: list[Day] = []
        d = START
        while len(out) < n:
            if d.weekday() < 5:
                out.append(
                    Day(
                        d,
                        self.rng.randint(250, 440),
                        self.rng.choice([2, 3, 3, 4]),
                        self.rng.choice([0, 0.5, 1.5, 2.25, 3.5, 4.75, 6, 8.5, 11.25]),
                        self.rng.randint(12, 26),
                        self.rng.randint(1, 6),
                    )
                )
            d += dt.timedelta(days=1)
        return out

    def name(self) -> str:
        return f"{self.fake.first_name()} {self.fake.last_name()}"

    def phone(self) -> str:
        return f"{self.rng.randint(201, 989)}-555-{self.rng.randint(100, 199):04d}"

    def email(self) -> str:
        return f"{self.fake.user_name()}@example.test"

    def mrn(self) -> str:
        return f"{self.rng.randint(10_000_000, 99_999_999)}"


def row(d: Day, *fields: str) -> dict[str, Any]:
    values = {
        DATE: d.date.isoformat(),
        PATIENTS: d.patients,
        STAFF: d.staff,
        OT: d.ot,
        MF: d.mf,
        SESSIONS: d.sessions,
    }
    return {f: values[f] for f in fields}


def to_csv(rows: list[list[Any]], delimiter: str = ",", encoding: str = "utf-8") -> bytes:
    buf = io.StringIO()
    csv.writer(buf, delimiter=delimiter, lineterminator="\n").writerows(rows)
    return buf.getvalue().encode(encoding)


def to_xlsx(
    sheets: dict[str, list[list[Any]]], merges: dict[str, list[str]] | None = None
) -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    first = True
    for title, rows in sheets.items():
        ws = wb.active if first else wb.create_sheet()
        assert ws is not None
        ws.title = title
        first = False
        for r in rows:
            ws.append(r)
        for m in (merges or {}).get(title, []):
            ws.merge_cells(m)
    # Fixed metadata so the same seed writes the same bytes.
    wb.properties.created = wb.properties.modified = dt.datetime(2026, 11, 2)
    wb.properties.creator = "sg data synth-messy"
    buf = io.BytesIO()
    wb.save(buf)
    return _fixed_zip_times(buf.getvalue())


def _fixed_zip_times(data: bytes) -> bytes:
    """openpyxl stamps each zip entry with the current time; pin it so bytes are stable."""
    src = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            fixed = zipfile.ZipInfo(info.filename, date_time=(2026, 11, 2, 0, 0, 0))
            fixed.compress_type = zipfile.ZIP_DEFLATED
            fixed.external_attr = info.external_attr
            body = src.read(info.filename)
            if info.filename == "docProps/core.xml":
                # openpyxl writes the save time as dcterms:modified
                body = re.sub(
                    rb"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", b"2026-11-02T00:00:00Z", body
                )
            dst.writestr(fixed, body)
    return out.getvalue()


def hm(hours: float) -> str:
    h = int(hours)
    return f"{h}:{round((hours - h) * 60):02d}"


# ---------------------------------------------------------------------------
# Cases
# ---------------------------------------------------------------------------


def abbreviated_headers(g: Gen) -> Case:
    days = g.days()
    rows: list[list[Any]] = [["Dt", "Pts", "AM staff", "OT hrs", "MF", "Sessions"]]
    for d in days:
        rows.append([d.date.isoformat(), d.patients, d.staff, d.ot, d.mf, d.sessions])
    rows[3][1] = "n/a"  # row 2 of the data cannot be read
    good = [row(d, DATE, PATIENTS, OT) for i, d in enumerate(days) if i != 2]
    return Case(
        "abbreviated_headers.csv",
        "messy",
        to_csv(rows),
        {
            "Dt": DATE,
            "Pts": PATIENTS,
            "AM staff": STAFF,
            "OT hrs": OT,
            "MF": MF,
            "Sessions": SESSIONS,
        },
        good,
        error_rows=[2],
    )


def misspelled_headers(g: Gen) -> Case:
    days = g.days()
    rows: list[list[Any]] = [["Date", "Regular patinets", "Morning staf", "Overtme hours"]]
    rows += [[d.date.isoformat(), d.patients, d.staff, d.ot] for d in days]
    return Case(
        "misspelled_headers.csv",
        "messy",
        to_csv(rows),
        {"Date": DATE, "Regular patinets": PATIENTS, "Morning staf": STAFF, "Overtme hours": OT},
        [row(d, DATE, PATIENTS, OT) for d in days],
    )


def exact_names(g: Gen) -> Case:
    days = g.days()
    header = [DATE, PATIENTS, STAFF, OT, MF, SESSIONS]
    rows: list[list[Any]] = [header]
    rows += [[d.date.isoformat(), d.patients, d.staff, d.ot, d.mf, d.sessions] for d in days]
    return Case(
        "exact_names.csv",
        "exact",
        to_csv(rows),
        {h: h for h in header},
        [row(d, DATE, PATIENTS, OT) for d in days],
    )


def synonym_headers(g: Gen) -> Case:
    days = g.days()
    header = [
        "Shift date",
        "Patient count",
        "Staff present",
        "Overtime hours",
        "MF cases",
        "Clinic sessions",
    ]
    rows: list[list[Any]] = [header]
    rows += [[d.date.isoformat(), d.patients, d.staff, d.ot, d.mf, d.sessions] for d in days]
    fields = [DATE, PATIENTS, STAFF, OT, MF, SESSIONS]
    return Case(
        "synonym_headers.csv",
        "exact",
        to_csv(rows),
        dict(zip(header, fields, strict=True)),
        [row(d, DATE, PATIENTS, OT) for d in days],
    )


def blank_rows_and_columns(g: Gen) -> Case:
    days = g.days()
    rows: list[list[Any]] = [[], [None, "Date", None, "Patients", "Staff present", "Overtime"]]
    for i, d in enumerate(days):
        rows.append([None, d.date.isoformat(), None, d.patients, d.staff, d.ot])
        if i % 2 == 1:
            rows.append([])
    return Case(
        "blank_rows_and_columns.xlsx",
        "exact",
        to_xlsx({"Log": rows}),
        {"Date": DATE, "Patients": PATIENTS, "Staff present": STAFF, "Overtime": OT},
        [row(d, DATE, PATIENTS, OT) for d in days],
    )


def two_row_merged_header(g: Gen) -> Case:
    days = g.days()
    rows: list[list[Any]] = [
        ["Weekly sterile log", None, None, None],
        ["Shift", "Patients", "Staff", "Overtime"],
        ["Date", "Regular", "Morning", "Hours"],
    ]
    rows += [[dt.datetime.combine(d.date, dt.time()), d.patients, d.staff, hm(d.ot)] for d in days]
    return Case(
        "two_row_merged_header.xlsx",
        "messy",
        to_xlsx({"Log": rows}, {"Log": ["A1:D1"]}),
        {
            "Shift Date": DATE,
            "Patients Regular": PATIENTS,
            "Staff Morning": STAFF,
            "Overtime Hours": OT,
        },
        [row(d, DATE, PATIENTS, OT) for d in days],
    )


def excel_serial_dates(g: Gen) -> Case:
    days = g.days()
    rows: list[list[Any]] = [["Date", "Patients", "Staff present", "OT hours"]]
    rows += [[(d.date - dt.date(1899, 12, 30)).days, d.patients, d.staff, d.ot] for d in days]
    return Case(
        "excel_serial_dates.xlsx",
        "exact",
        to_xlsx({"Log": rows}),
        {"Date": DATE, "Patients": PATIENTS, "Staff present": STAFF, "OT hours": OT},
        [row(d, DATE, PATIENTS, OT) for d in days],
    )


def mixed_date_formats(g: Gen) -> Case:
    days = g.days()
    fmts: list[Callable[[dt.date], str]] = [
        lambda d: d.strftime("%m/%d/%y"),
        lambda d: d.isoformat(),
        lambda d: d.strftime("%b %d").replace(" 0", " "),
    ]
    rows: list[list[Any]] = [["Date", "Patients", "Staff present", "Overtime"]]
    rows += [[fmts[i % 3](d.date), d.patients, d.staff, d.ot] for i, d in enumerate(days)]
    return Case(
        "mixed_date_formats.csv",
        "exact",
        to_csv(rows),
        {"Date": DATE, "Patients": PATIENTS, "Staff present": STAFF, "Overtime": OT},
        [row(d, DATE, PATIENTS, OT) for d in days],
    )


def mixed_durations(g: Gen) -> Case:
    days = g.days()
    fmts: list[Callable[[float], str]] = [
        lambda h: f"{int(h)}h{round((h - int(h)) * 60):02d}",
        hm,
        lambda h: f"{h:g}",
        lambda h: f"{round(h * 60)} min",
        lambda h: f"{h:g} hrs",
    ]
    rows: list[list[Any]] = [["Date", "Patients", "Staff present", "Overtime"]]
    rows += [
        [d.date.isoformat(), d.patients, d.staff, fmts[i % 5](d.ot)] for i, d in enumerate(days)
    ]
    return Case(
        "mixed_durations.csv",
        "exact",
        to_csv(rows),
        {"Date": DATE, "Patients": PATIENTS, "Staff present": STAFF, "Overtime": OT},
        [row(d, DATE, PATIENTS, OT) for d in days],
    )


def wide_days_as_columns(g: Gen) -> Case:
    days = g.days(5)
    header: list[Any] = ["Measure", *[d.date.strftime("%m/%d/%Y") for d in days]]
    rows: list[list[Any]] = [
        header,
        ["Patients", *[d.patients for d in days]],
        ["Staff present", *[d.staff for d in days]],
        ["OT hours", *[d.ot for d in days]],
        ["MF cases", *[d.mf for d in days]],
    ]
    return Case(
        "wide_days_as_columns.csv",
        "messy",
        to_csv(rows),
        {
            "date": DATE,
            "Patients": PATIENTS,
            "Staff present": STAFF,
            "OT hours": OT,
            "MF cases": MF,
        },
        [row(d, DATE, PATIENTS, OT) for d in days],
    )


def employee_names_column(g: Gen) -> Case:
    days = g.days()
    names = [g.name() for _ in days]
    rows: list[list[Any]] = [["Date", "Employee", "Patients", "Staff present", "Overtime"]]
    rows += [
        [d.date.isoformat(), n, d.patients, d.staff, d.ot] for d, n in zip(days, names, strict=True)
    ]
    return Case(
        "employee_names_column.csv",
        "exact",
        to_csv(rows),
        {"Date": DATE, "Patients": PATIENTS, "Staff present": STAFF, "Overtime": OT},
        [row(d, DATE, PATIENTS, OT) for d in days],
        dropped_columns=["Employee"],
        fake_strings=names,
    )


def phi_in_notes(g: Gen) -> Case:
    days = g.days()
    phone, email, mrn = g.phone(), g.email(), g.mrn()
    notes: list[str | None] = [
        f"call {phone} about the late cart",
        "washer slow after lunch",
        f"emailed {email} about trays",
        None,
        f"chart MRN {mrn} returned to clinic",
        "sterilizer cycle rerun",
    ]
    rows: list[list[Any]] = [["Date", "Patients", "Staff present", "Overtime", "Notes"]]
    rows += [
        [d.date.isoformat(), d.patients, d.staff, d.ot, n] for d, n in zip(days, notes, strict=True)
    ]
    return Case(
        "phi_in_notes.csv",
        "exact",
        to_csv(rows),
        {
            "Date": DATE,
            "Patients": PATIENTS,
            "Staff present": STAFF,
            "Overtime": OT,
            "Notes": NOTES,
        },
        [row(d, DATE, PATIENTS, OT) for d in days],
        error_rows=[0, 2, 4],
        phi_cells=[
            {"entity_type": "PHONE_NUMBER", "column": "Notes", "row": 0},
            {"entity_type": "EMAIL_ADDRESS", "column": "Notes", "row": 2},
            {"entity_type": "MRN", "column": "Notes", "row": 4},
        ],
        fake_strings=[phone, email, mrn],
    )


def multiple_sheets(g: Gen) -> Case:
    days = g.days()
    rows: list[list[Any]] = [["Date", "Patients", "Staff present", "Overtime"]]
    rows += [[d.date.isoformat(), d.patients, d.staff, d.ot] for d in days]
    sheets = {
        "Read me": [["Fill one row per day"]],
        "Week log": rows,
        "Lookups": [["a", 1], ["b", 2]],
    }
    return Case(
        "multiple_sheets.xlsx",
        "exact",
        to_xlsx(sheets),
        {"Date": DATE, "Patients": PATIENTS, "Staff present": STAFF, "Overtime": OT},
        [row(d, DATE, PATIENTS, OT) for d in days],
    )


def semicolon_latin1(g: Gen) -> Case:
    days = g.days()
    rows: list[list[Any]] = [["Date", "Patients", "Staff present", "Overtime", "Notes"]]
    notes = ["café delivered late", None, "sterilizer reprise", None, "naïve check", None]
    rows += [
        [d.date.isoformat(), d.patients, d.staff, str(d.ot).replace(".", ","), n]
        for d, n in zip(days, notes, strict=True)
    ]
    return Case(
        "semicolon_latin1.csv",
        "exact",
        to_csv(rows, ";", "latin-1"),
        {
            "Date": DATE,
            "Patients": PATIENTS,
            "Staff present": STAFF,
            "Overtime": OT,
            "Notes": NOTES,
        },
        [row(d, DATE, PATIENTS, OT) for d in days],
    )


def totals_row(g: Gen) -> Case:
    days = g.days()
    rows: list[list[Any]] = [["Date", "Patients", "Staff present", "Overtime"]]
    rows += [[d.date.isoformat(), d.patients, d.staff, d.ot] for d in days]
    rows.append(["Total", sum(d.patients for d in days), None, sum(d.ot for d in days)])
    return Case(
        "totals_row.xlsx",
        "exact",
        to_xlsx({"Log": rows}),
        {"Date": DATE, "Patients": PATIENTS, "Staff present": STAFF, "Overtime": OT},
        [row(d, DATE, PATIENTS, OT) for d in days],
    )


def duplicate_dates(g: Gen) -> Case:
    days = g.days()
    rows: list[list[Any]] = [["Date", "Patients", "Staff present", "Overtime"]]
    rows += [[d.date.isoformat(), d.patients, d.staff, d.ot] for d in days]
    rows.append([days[1].date.isoformat(), 300, 3, 1.0])  # the same day logged twice
    return Case(
        "duplicate_dates.csv",
        "exact",
        to_csv(rows),
        {"Date": DATE, "Patients": PATIENTS, "Staff present": STAFF, "Overtime": OT},
        [row(d, DATE, PATIENTS, OT) for d in days],
        error_rows=[len(days)],
    )


def punch_out_times(g: Gen) -> Case:
    days = g.days(4)
    people = [g.name() for _ in range(3)]
    rows: list[list[Any]] = [["Date", "Employee", "Clock out", "Patients", "Staff present"]]
    expected: list[dict[str, Any]] = []
    for d in days:
        total = 0.0
        for p in people:
            minutes = g.rng.choice([0, 30, 90, 150, 240, 300])
            out = dt.datetime.combine(d.date, dt.time(15, 0)) + dt.timedelta(minutes=minutes)
            rows.append(
                [d.date.strftime("%m/%d/%y"), p, out.strftime("%H:%M"), d.patients, d.staff]
            )
            total += minutes / 60
        expected.append({DATE: d.date.isoformat(), PATIENTS: d.patients, OT: round(total, 2)})
    return Case(
        "punch_out_times.csv",
        "exact",
        to_csv(rows),
        {"Date": DATE, "Clock out": None, "Patients": PATIENTS, "Staff present": STAFF},
        expected,
        dropped_columns=["Employee"],
        fake_strings=people,
    )


CASES: tuple[Callable[[Gen], Case], ...] = (
    exact_names,
    synonym_headers,
    abbreviated_headers,
    misspelled_headers,
    blank_rows_and_columns,
    two_row_merged_header,
    excel_serial_dates,
    mixed_date_formats,
    mixed_durations,
    wide_days_as_columns,
    employee_names_column,
    phi_in_notes,
    multiple_sheets,
    semicolon_latin1,
    totals_row,
    duplicate_dates,
    punch_out_times,
)


def generate(out: Path, seed: int = 7) -> list[Path]:
    """Write every case and its expected.json into `out` (created if needed)."""
    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for make in CASES:
        case = make(Gen(seed))
        path = out / case.name
        path.write_bytes(case.data)
        exp = out / f"{case.name}.expected.json"
        exp.write_text(json.dumps(case.expected(), indent=2) + "\n", encoding="utf-8", newline="\n")
        written += [path, exp]
    return written
