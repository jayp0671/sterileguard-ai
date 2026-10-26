"""Plain-language driver sentences (SG-14).

Each sentence is an i18n key `drivers.<feature>.<pos|neg>` with parameters {value} and {hours};
the web translates it client-side from apps/web/src/messages/<locale>.json and the API also
returns the default English sentence built here. A test keeps en.json identical to TEMPLATES.
Templates use ICU message syntax; `{value, plural, one {...} other {...}}` is supported here.
"""

from __future__ import annotations

import re
from typing import Any

from sg_data.schema import BY_NAME, TIER2_INPUTS
from sg_ml.explain import OTHER
from sg_ml.features import F

POS = "is adding about {hours} hours"
NEG = "is reducing overtime by about {hours} hours"

# Sentence subjects; the verb phrase depends on the sign of the contribution.
SUBJECTS: dict[str, str] = {
    F.regular_patients: "{value} scheduled patients",
    F.morning_staff_present: "{value} staff at 7:00 AM",
    F.mf_cases: "{value} MF cases",
    F.student_clinic_sessions: "{value} student clinic sessions",
    F.aft_11_staff: "{value} staff starting at 11:00",
    F.aft_13_staff: "{value} staff starting at 1:00 PM",
    F.aft_15_staff: "{value} staff starting at 3:00 PM",
    F.outside_support_staff: "{value} outside support staff",
    F.ot_available_staff: "{value} staff willing to stay",
    F.washers_up: "{value, plural, one {Only # washer working} other {# washers working}}",
    F.sterilizers_up: (
        "{value, plural, one {Only # sterilizer available} other {# sterilizers available}}"
    ),
    F.carryover_backlog_estimate: "Carryover backlog of {value}",
    F.is_holiday: "Holiday or school closure",
    F.academic_event: "Academic event ({value})",
    "total_afternoon_staff": "{value} afternoon staff",
    "staff_hours_before_15": "{value} staff hours before 3:00 PM",
    "patients_per_morning_staff": "{value} patients per morning staff member",
    "demand_units_est": "Expected workload of {value} work units",
    "capacity_ratio": "Workload of {value} units per staff hour",
    "day_of_week": "The {value} schedule",
    "is_monday": "Monday",
    "is_friday": "Friday",
    "week_of_semester": "Week {value} of the term",
    "ot_hours_prev_day": "Overtime of {value} hours on the previous workday",
    "ot_hours_7d_mean": "Average overtime of {value} hours over the past week",
    OTHER: "Other factors",
    **{
        f"{n}__missing": f"Using the department default for {BY_NAME[n].label.lower()}"
        for n in TIER2_INPUTS
    },
}

TEMPLATES: dict[str, dict[str, str]] = {
    feature: {"pos": f"{subject} {POS}", "neg": f"{subject} {NEG}"}
    for feature, subject in SUBJECTS.items()
}

WEEKDAY_NAMES = {
    "mon": "Monday",
    "tue": "Tuesday",
    "wed": "Wednesday",
    "thu": "Thursday",
    "fri": "Friday",
    "sat": "Saturday",
    "sun": "Sunday",
}

_PLURAL = re.compile(r"\{value, plural, one \{([^}]*)\} other \{([^}]*)\}\}")


def text_key(feature: str, contribution: float) -> str:
    return f"drivers.{feature}.{'pos' if contribution >= 0 else 'neg'}"


def display_value(feature: str, value: Any) -> str:
    if value is None:
        return ""
    if feature == "day_of_week":
        return WEEKDAY_NAMES.get(str(value), str(value))
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.0f}" if value.is_integer() else f"{value:.1f}"
    return str(value)


def text_params(feature: str, value: Any, contribution: float) -> dict[str, Any]:
    params: dict[str, Any] = {"hours": round(abs(contribution), 1)}
    shown = display_value(feature, value)
    try:
        params["value"] = float(shown) if "." in shown else int(shown)
    except ValueError:
        params["value"] = shown
    return params


def render(template: str, params: dict[str, Any]) -> str:
    """Format an ICU-lite template with plural support for {value}."""

    def plural(m: re.Match[str]) -> str:
        one, other = m.group(1), m.group(2)
        chosen = one if params.get("value") == 1 else other
        return chosen.replace("#", str(params.get("value")))

    out = _PLURAL.sub(plural, template)
    for k, v in params.items():
        out = out.replace("{" + k + "}", f"{v:g}" if isinstance(v, float) else str(v))
    return out


def sentence(feature: str, value: Any, contribution: float) -> tuple[str, dict[str, Any], str]:
    """(text_key, text_params, default English sentence) for one driver."""
    if feature not in TEMPLATES:
        raise KeyError(f"no driver sentence for {feature}")
    sign = "pos" if contribution >= 0 else "neg"
    params = text_params(feature, value, contribution)
    return text_key(feature, contribution), params, render(TEMPLATES[feature][sign], params)
