"""Golden cases for the agent evals (SG-23, SG-26 Part B). Synthetic only.

Briefing: 20 forecast inputs x 2 locales, plus adversarial answers the guardrail must reject.
Mapping: synthetic daily-log files whose headers deterministic matching cannot resolve, with a
planted names column and a free-text column that must never be sent.

Cassettes for these cases are written by make_cassettes.py. Until someone records them live
(NIM_MODE=record with a key), the answers are hand-written stand-ins marked "stand_in": true;
they exercise the parsing, guardrail and fallback paths, not the model's quality.
"""

# ruff: noqa: E501 (golden strings and stand-in answers read better unwrapped)

from __future__ import annotations

import random
from typing import Any

DRIVER_TEXTS = [
    ("regular_patients", "More patients than usual ({v} scheduled)"),
    ("ot_available_staff", "Only {v} staff willing to stay late"),
    ("sterilizers_up", "One sterilizer is down ({v} running)"),
    ("student_clinic_sessions", "{v} student clinic sessions scheduled"),
    ("aft_11_staff", "Fewer afternoon staff at 11:00 ({v})"),
    ("mf_cases", "{v} maxillofacial cases"),
    ("washers_up", "Both washers running ({v})"),
]


def forecast(i: int) -> dict[str, Any]:
    rng = random.Random(1000 + i)
    p50 = round(rng.uniform(0.5, 18.0), 1)
    p10 = round(max(0.0, p50 - rng.uniform(0.4, 2.5)), 1)
    p90 = round(p50 + rng.uniform(0.4, 3.0), 1)
    cls = "low" if p50 <= 5.67 else "moderate" if p50 <= 12.13 else "high"
    prob = round(rng.uniform(0.5, 0.97), 2)
    picks = rng.sample(DRIVER_TEXTS, 3)
    values = {
        "regular_patients": rng.randint(300, 442),
        "ot_available_staff": rng.randint(1, 3),
        "sterilizers_up": 1,
        "student_clinic_sessions": rng.randint(2, 6),
        "aft_11_staff": rng.randint(1, 3),
        "mf_cases": rng.randint(12, 26),
        "washers_up": 2,
    }
    drivers = [
        {
            "rank": r + 1,
            "feature": feat,
            "contribution_hours": round(rng.uniform(-1.5, 4.0), 2),
            "default_text": text.format(v=values[feat]),
        }
        for r, (feat, text) in enumerate(picks)
    ]
    out: dict[str, Any] = {
        "target_date": f"2026-11-{(i % 20) + 2:02d}",
        "ot_p10": p10,
        "ot_p50": p50,
        "ot_p90": p90,
        "burden_class": cls,
        "burden_probs": {cls: prob},
        "drivers": drivers,
    }
    if i % 3 == 0 and cls != "low":
        to = round(max(0.5, p50 - rng.uniform(2, 5)), 1)
        out["minimum_change"] = {"text": "Adding 1 person at 11:00", "from_p50": p50, "to_p50": to}
    return out


BRIEFING_CASES = [forecast(i) for i in range(20)]
LOCALES = ("en", "es")

# Adversarial answers: each breaks exactly one rule; the guardrail must reject all of them.
ADVERSARIAL = {
    "invented_number": "Tomorrow looks heavy with about 14.2 hours of overtime and 3 extra trays. Model estimate.",
    "person_name": "Ask Maria Gonzalez to stay late tomorrow; overtime is likely high. Model estimate.",
    "too_long": ("Tomorrow is a busy day in the department. " * 16) + "Model estimate.",
    "missing_ending": "Tomorrow's overtime is likely moderate, driven mostly by patient volume.",
    "url": "Overtime is likely moderate; see https://example.com/staffing for details. Model estimate.",
    "phone": "Overtime is likely high; call 201-555-0147 to arrange cover. Model estimate.",
}

# Mapping: each case is a synthetic CSV plus the expected field for every header.
MAPPING_CASES: list[dict[str, Any]] = [
    {
        "name": "shorthand_log",
        "csv": "Date,Pts seen,Folks on AM,Extra hrs,Clinic blocks\n"
        "2026-10-12,332,3,6,4\n2026-10-13,268,2,4.75,3\n2026-10-14,379,3,0,5\n",
        "expected": {
            "Date": "date",
            "Pts seen": "regular_patients",
            "Folks on AM": "morning_staff_present",
            "Extra hrs": "ot_labor_hours",
            "Clinic blocks": "student_clinic_sessions",
        },
    },
    {
        "name": "equipment_log",
        "csv": "Date,Patients,Staff present,Overtime,Autoclaves running,Rinse machines up,Employee\n"
        "2026-10-12,332,3,6,2,2,Mario Hernandez\n2026-10-13,268,2,4.75,1,2,Debra Jones\n"
        "2026-10-14,379,3,0,2,1,Amanda Diaz\n",
        "expected": {
            "Date": "date",
            "Patients": "regular_patients",
            "Staff present": "morning_staff_present",
            "Overtime": "ot_labor_hours",
            "Autoclaves running": "sterilizers_up",
            "Rinse machines up": "washers_up",
        },
    },
    {
        "name": "afternoon_cover",
        "csv": "Date,Patients,Staff present,Overtime,Noon crew,1pm crew,Late crew,Stay-late volunteers,Comments\n"
        "2026-10-12,332,3,6,3,1,2,2,cart late\n2026-10-13,268,3,4.75,3,1,2,1,washer slow\n"
        "2026-10-14,379,3,0,2,1,2,3,\n",
        "expected": {
            "Date": "date",
            "Patients": "regular_patients",
            "Staff present": "morning_staff_present",
            "Overtime": "ot_labor_hours",
            "Noon crew": "aft_11_staff",
            "1pm crew": "aft_13_staff",
            "Late crew": "aft_15_staff",
            "Stay-late volunteers": "ot_available_staff",
            "Comments": "notes",
        },
    },
    {
        "name": "surgery_counts",
        "csv": "Date,Patients,Staff present,Overtime,Oral surgery cases,Help from other depts,"
        "Backlog level,Shift remarks\n"
        "2026-10-12,332,3,6,20,2,1,cart late again\n2026-10-13,268,2,4.75,18,2,0,washer slow\n"
        "2026-10-14,379,3,0,22,1,2,quiet day\n",
        "expected": {
            "Date": "date",
            "Patients": "regular_patients",
            "Staff present": "morning_staff_present",
            "Overtime": "ot_labor_hours",
            "Oral surgery cases": "mf_cases",
            "Help from other depts": "outside_support_staff",
            "Backlog level": "carryover_backlog_estimate",
            "Shift remarks": "notes",
        },
    },
]
