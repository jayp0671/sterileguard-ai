"""Canonical data schema (SG-08, plan §8.1, §10.0).

This module is the ONLY place in the repo that lists the shift fields. Validation (pandera),
API models (Pydantic -> OpenAPI -> TypeScript), the simulator's day inputs, and the database
drift test are all generated from FIELDS. A repo scan test fails if another file re-lists them.

Column names match docs/domain/daily-log-template.csv exactly. Ranges follow the SG-08 ticket
and docs/domain/data-dictionary.md; adjust them here, nowhere else.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field, replace
from typing import Any, Literal

import pandas as pd
import pandera.pandas as pa
from pydantic import BaseModel, Field, create_model, model_validator

DType = Literal["int", "float", "bool", "date", "enum", "str", "uuid"]
Role = Literal["input", "outcome", "meta"]
Tier = Literal[0, 1, 2, 3]

SOURCES = ("real", "simulated")
ACADEMIC_EVENTS = ("none", "exam", "break", "semester_start")


@dataclass(frozen=True)
class FieldSpec:
    name: str
    dtype: DType
    tier: Tier
    role: Role
    description: str
    unit: str = ""
    min: float | None = None
    max: float | None = None
    enum_values: tuple[str, ...] = ()
    # Dotted path into departments.settings (Tier 2 inputs only). A path segment matching the
    # "key" of an item in a list (shift_windows) selects that item.
    default_from: str | None = None
    # Used when the department settings do not contain default_from.
    fallback: Any = None
    # Settings key that tightens max per department (equipment counts).
    max_from: str | None = None
    max_length: int | None = None
    nullable: bool = False
    synonyms: tuple[str, ...] = field(default_factory=tuple)
    # UI metadata for inputs (exported through OpenAPI so the web form is generated from it)
    label: str = ""
    group: str = ""

    @property
    def required(self) -> bool:
        """Tier 1 fields and non-nullable meta fields must be present."""
        return self.tier == 1 or (self.role == "meta" and not self.nullable)


def _staff(name: str, tier: Tier, description: str, **kw: Any) -> FieldSpec:
    return FieldSpec(name, "int", tier, "input", description, unit="people", min=0, max=20, **kw)


FIELDS: tuple[FieldSpec, ...] = (
    # meta
    FieldSpec("department_id", "uuid", 0, "meta", "Department the row belongs to"),
    FieldSpec("source", "enum", 0, "meta", "Where the row came from", enum_values=SOURCES),
    FieldSpec("dataset_id", "uuid", 0, "meta", "Dataset lineage", nullable=True),
    FieldSpec("created_by", "uuid", 0, "meta", "User who created the row", nullable=True),
    # Tier 1
    FieldSpec(
        "date",
        "date",
        1,
        "input",
        "Calendar date of the shift",
        unit="YYYY-MM-DD",
        synonyms=("day", "shift date", "shift_date", "plan date"),
    ),
    FieldSpec(
        "regular_patients",
        "int",
        1,
        "input",
        "Scheduled regular patients (emergency and intake excluded)",
        unit="patients",
        min=0,
        max=800,
        synonyms=(
            "patients",
            "pts",
            "regular pts",
            "patient count",
            "# patients",
            "scheduled patients",
        ),
    ),
    _staff(
        "morning_staff_present",
        1,
        "Dental Central Sterile staff present for the morning operation",
        synonyms=("employees", "morning staff", "staff present", "am staff"),
    ),
    FieldSpec(
        "ot_labor_hours",
        "float",
        1,
        "outcome",
        "Hours past 3:00 PM, summed over morning staff",
        unit="hours",
        min=0,
        max=60,
        synonyms=("overtime", "ot", "ot hours", "overtime hours"),
    ),
    # Tier 2 inputs
    FieldSpec(
        "mf_cases",
        "int",
        2,
        "input",
        "Maxillofacial surgery cases scheduled",
        unit="cases",
        min=0,
        max=80,
        default_from="mf_cases_default",
        fallback=20,
        synonyms=("mf", "maxillofacial cases", "mf surgeries", "omfs cases"),
    ),
    FieldSpec(
        "student_clinic_sessions",
        "int",
        2,
        "input",
        "Scheduled student clinic sessions",
        unit="sessions",
        min=0,
        max=40,
        default_from="student_clinic_sessions_default",
        fallback=0,
        synonyms=("sessions", "student sessions", "clinic sessions"),
    ),
    _staff(
        "aft_11_staff",
        2,
        "Staff starting about 11:00 AM",
        default_from="shift_windows.aft_11.default_staff",
        fallback=3,
        synonyms=("11am staff", "11:00 staff", "aft 11"),
    ),
    _staff(
        "aft_13_staff",
        2,
        "Staff starting about 1:00 PM",
        default_from="shift_windows.aft_13.default_staff",
        fallback=1,
        synonyms=("1pm staff", "13:00 staff", "aft 13"),
    ),
    _staff(
        "aft_15_staff",
        2,
        "Staff starting at the regular afternoon start (3:00 PM)",
        default_from="shift_windows.aft_15.default_staff",
        fallback=2,
        synonyms=("3pm staff", "15:00 staff", "aft 15", "afternoon staff"),
    ),
    _staff(
        "outside_support_staff",
        2,
        "Outside-department helpers (until about 8 PM)",
        default_from="outside_support_default",
        fallback=2,
        synonyms=("outside support", "support staff", "helpers"),
    ),
    _staff(
        "ot_available_staff",
        2,
        "Morning staff who agreed to stay for overtime",
        default_from="ot_available_default",
        fallback=0,
        synonyms=("ot available", "willing to stay", "stayers"),
    ),
    FieldSpec(
        "washers_up",
        "int",
        2,
        "input",
        "Washer-disinfectors working at 7:00 AM",
        unit="machines",
        min=0,
        max=10,
        default_from="washers",
        fallback=2,
        max_from="washers",
        synonyms=("washers", "washers working"),
    ),
    FieldSpec(
        "sterilizers_up",
        "int",
        2,
        "input",
        "Sterilizers working at 7:00 AM",
        unit="machines",
        min=0,
        max=10,
        default_from="sterilizers",
        fallback=2,
        max_from="sterilizers",
        synonyms=("sterilizers", "sterilizers working", "autoclaves"),
    ),
    FieldSpec(
        "carryover_backlog_estimate",
        "int",
        2,
        "input",
        "Work waiting at 7:00 AM (0 light, 1 normal, 2 heavy)",
        unit="scale 0-2",
        min=0,
        max=2,
        default_from="carryover_default",
        fallback=1,
        synonyms=("carryover", "backlog", "backlog estimate"),
    ),
    FieldSpec(
        "is_holiday",
        "bool",
        2,
        "input",
        "Holiday or school closed",
        default_from="is_holiday_default",
        fallback=False,
        synonyms=("holiday", "closed"),
    ),
    FieldSpec(
        "academic_event",
        "enum",
        2,
        "input",
        "Academic calendar event",
        enum_values=ACADEMIC_EVENTS,
        default_from="academic_event_default",
        fallback="none",
        synonyms=("event", "academic calendar"),
    ),
    # Tier 3 outcomes (calibration and analysis only, never model inputs)
    FieldSpec(
        "emergency_intake_patients",
        "int",
        3,
        "outcome",
        "Emergency and intake patients",
        unit="patients",
        min=0,
        max=200,
        nullable=True,
        synonyms=("emergency", "intake", "walk-ins", "emergency patients"),
    ),
    FieldSpec(
        "returned_unused_estimate",
        "int",
        3,
        "outcome",
        "Issued but unused sets returned",
        unit="sets",
        min=0,
        max=2000,
        nullable=True,
        synonyms=("returned unused", "unused sets"),
    ),
    FieldSpec(
        "equipment_downtime_minutes",
        "int",
        3,
        "outcome",
        "Washer and sterilizer downtime",
        unit="minutes",
        min=0,
        max=900,
        nullable=True,
        synonyms=("downtime", "downtime minutes"),
    ),
    FieldSpec(
        "notes",
        "str",
        3,
        "outcome",
        "Short operational notes, never names",
        max_length=500,
        nullable=True,
        synonyms=("comments", "remarks"),
    ),
)

# Short form labels and form sections for the plan inputs (SG-11). Sections: demand,
# staffing, equipment, carryover.
_UI: dict[str, tuple[str, str]] = {
    "regular_patients": ("Regular patients", "demand"),
    "mf_cases": ("MF cases", "demand"),
    "student_clinic_sessions": ("Student clinic sessions", "demand"),
    "is_holiday": ("Holiday or school closed", "demand"),
    "academic_event": ("Academic event", "demand"),
    "morning_staff_present": ("7:00 AM staff", "staffing"),
    "aft_11_staff": ("11:00 AM start", "staffing"),
    "aft_13_staff": ("1:00 PM start", "staffing"),
    "aft_15_staff": ("3:00 PM start", "staffing"),
    "outside_support_staff": ("Outside support", "staffing"),
    "ot_available_staff": ("Staff willing to stay for overtime", "staffing"),
    "washers_up": ("Washers working", "equipment"),
    "sterilizers_up": ("Sterilizers working", "equipment"),
    "carryover_backlog_estimate": ("Backlog at 7:00 AM", "carryover"),
}
FIELDS = tuple(
    replace(f, label=_UI[f.name][0], group=_UI[f.name][1]) if f.name in _UI else f for f in FIELDS
)

BY_NAME: dict[str, FieldSpec] = {f.name: f for f in FIELDS}


def fields(*, roles: set[Role] | None = None, tiers: set[int] | None = None) -> list[FieldSpec]:
    return [
        f
        for f in FIELDS
        if (roles is None or f.role in roles) and (tiers is None or f.tier in tiers)
    ]


def names(*, roles: set[Role] | None = None, tiers: set[int] | None = None) -> list[str]:
    return [f.name for f in fields(roles=roles, tiers=tiers)]


INPUT_FIELDS = names(roles={"input"})  # includes date
TIER2_INPUTS = names(roles={"input"}, tiers={2})
OUTCOME_FIELDS = names(roles={"outcome"})
META_FIELDS = names(roles={"meta"})


# ---------------------------------------------------------------------------
# Cross-field rules (shared by pandera and Pydantic)
# ---------------------------------------------------------------------------

CROSS_FIELD_MESSAGE = "ot_available_staff must not exceed morning_staff_present"


def ot_available_ok(ot_available: Any, morning: Any) -> bool:
    if ot_available is None or morning is None:
        return True
    if pd.isna(ot_available) or pd.isna(morning):
        return True
    return bool(ot_available <= morning)


# ---------------------------------------------------------------------------
# pandera
# ---------------------------------------------------------------------------

_PANDAS_DTYPE: dict[str, Any] = {
    "int": "Int64",
    "float": float,
    "bool": "boolean",
    "date": "datetime64[ns]",
    "enum": str,
    "str": str,
    "uuid": str,
}


def _column(spec: FieldSpec, settings: dict[str, Any] | None) -> pa.Column:
    checks: list[pa.Check] = []
    hi = spec.max
    if spec.max_from and settings and isinstance(settings.get(spec.max_from), int | float):
        hi = float(settings[spec.max_from])
    if spec.min is not None:
        checks.append(pa.Check.ge(spec.min, error=f"{spec.name} must be >= {spec.min:g}"))
    if hi is not None:
        checks.append(pa.Check.le(hi, error=f"{spec.name} must be <= {hi:g}"))
    if spec.enum_values:
        checks.append(
            pa.Check.isin(
                list(spec.enum_values), error=f"{spec.name} must be one of {spec.enum_values}"
            )
        )
    if spec.max_length:
        checks.append(
            pa.Check.str_length(
                max_value=spec.max_length, error=f"{spec.name} longer than {spec.max_length}"
            )
        )
    return pa.Column(
        _PANDAS_DTYPE[spec.dtype],
        checks=checks,
        nullable=not spec.required,
        required=spec.required,
        coerce=True,
        description=spec.description,
    )


def _unique_real(df: pd.DataFrame) -> bool:
    if not {"department_id", "date", "source"} <= set(df.columns):
        return True
    real = df[df["source"] == "real"]
    return not real.duplicated(subset=["department_id", "date", "source"]).any()


def to_pandera(
    role_set: set[Role] | None = None, settings: dict[str, Any] | None = None
) -> pa.DataFrameSchema:
    """Validation schema for a frame holding the given roles (default: all).

    Returns a DataFrameSchema, the object form of a DataFrameModel, because the columns are
    generated at runtime. Tier 1 columns are required; Tier 2 and 3 may be missing or null.
    """
    specs = fields(roles=role_set) if role_set else list(FIELDS)
    cols = {s.name: _column(s, settings) for s in specs}
    present = {s.name for s in specs}
    checks: list[pa.Check] = []
    if {"ot_available_staff", "morning_staff_present"} <= present:
        checks.append(
            pa.Check(
                lambda df: pd.Series(
                    [
                        ot_available_ok(a, m)
                        for a, m in zip(
                            df.get("ot_available_staff", pd.Series(dtype=float)),
                            df.get("morning_staff_present", pd.Series(dtype=float)),
                            strict=False,
                        )
                    ],
                    index=df.index,
                ),
                error=CROSS_FIELD_MESSAGE,
            )
        )
    if {"department_id", "date", "source"} <= present:
        checks.append(
            pa.Check(_unique_real, error="duplicate real row for (department_id, date, source)")
        )
    return pa.DataFrameSchema(cols, checks=checks, strict=False, name="shift_rows")


# ---------------------------------------------------------------------------
# Pydantic
# ---------------------------------------------------------------------------

PydanticKind = Literal["plan_in", "plan_values", "actual_in", "row"]

_PY_TYPE: dict[str, Any] = {
    "int": int,
    "float": float,
    "bool": bool,
    "date": dt.date,
    "str": str,
    "uuid": str,
}


def _py_type(spec: FieldSpec) -> Any:
    if spec.dtype == "enum":
        return Literal[spec.enum_values]
    return _PY_TYPE[spec.dtype]


def _field_def(spec: FieldSpec, *, required: bool) -> tuple[Any, Any]:
    kw: dict[str, Any] = {"description": spec.description}
    if spec.min is not None:
        kw["ge"] = spec.min
    if spec.max is not None:
        kw["le"] = spec.max
    if spec.max_length:
        kw["max_length"] = spec.max_length
    extra: dict[str, Any] = {"tier": spec.tier}
    if spec.unit:
        extra["unit"] = spec.unit
    if spec.label:
        extra["x-label"] = spec.label
        extra["x-group"] = spec.group
    kw["json_schema_extra"] = extra
    typ = _py_type(spec)
    if required:
        return (typ, Field(..., **kw))
    return (typ | None, Field(None, **kw))


class _CrossFieldBase(BaseModel):
    @model_validator(mode="after")
    def _ot_available_le_morning(self) -> _CrossFieldBase:
        if not ot_available_ok(
            getattr(self, "ot_available_staff", None), getattr(self, "morning_staff_present", None)
        ):
            raise ValueError(CROSS_FIELD_MESSAGE)
        return self


_MODEL_NAMES = {
    "plan_in": "ShiftPlanIn",
    "plan_values": "ShiftPlanValues",
    "actual_in": "ShiftActualIn",
    "row": "ShiftRow",
}
_MODEL_CACHE: dict[str, type[BaseModel]] = {}


def to_pydantic(kind: PydanticKind) -> type[BaseModel]:
    """ShiftPlanIn (inputs, date comes from the path), ShiftPlanValues (the same inputs, all
    optional, for suggestions with gaps), ShiftActualIn (outcomes), ShiftRow (all)."""
    if kind in _MODEL_CACHE:
        return _MODEL_CACHE[kind]
    if kind in ("plan_in", "plan_values"):
        specs = [s for s in fields(roles={"input"}) if s.name != "date"]
    elif kind == "actual_in":
        specs = fields(roles={"outcome"})
    else:
        specs = list(FIELDS)
    defs = {s.name: _field_def(s, required=s.required and kind != "plan_values") for s in specs}
    model = create_model(  # type: ignore[call-overload]
        _MODEL_NAMES[kind], __base__=_CrossFieldBase, **defs
    )
    _MODEL_CACHE[kind] = model
    return model  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# Database mapping (used by the drift test and to write migration 0004)
# ---------------------------------------------------------------------------

_SQL_TYPE: dict[str, str] = {
    "int": "integer",
    "float": "numeric",
    "bool": "boolean",
    "date": "date",
    "enum": "text",
    "str": "text",
    "uuid": "uuid",
}


def db_columns(table: Literal["shift_plans", "shift_actuals"]) -> dict[str, str]:
    """Expected schema-derived columns and their information_schema data_type.

    shift_plans holds every input (date stored as plan_date) plus a <field>__missing flag per
    Tier 2 input. shift_actuals holds every outcome (date stored as shift_date).
    """
    out: dict[str, str] = {}
    if table == "shift_plans":
        for s in fields(roles={"input"}):
            out["plan_date" if s.name == "date" else s.name] = _SQL_TYPE[s.dtype]
        for name in TIER2_INPUTS:
            out[f"{name}__missing"] = "boolean"
    else:
        out["shift_date"] = "date"
        for s in fields(roles={"outcome"}):
            out[s.name] = _SQL_TYPE[s.dtype]
    for s in fields(roles={"meta"}):
        out[s.name] = _SQL_TYPE[s.dtype]
    return out
