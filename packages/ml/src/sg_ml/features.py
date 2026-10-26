"""Feature registry (SG-13, plan §12.2).

Every model feature is registered here with known_at_7am. Schema inputs come from sg_data (the
only place shift fields are listed); engineered, calendar, lag and __missing features are added
on top. build_matrix refuses any feature that is not known at 7:00 AM, any outcome or Tier 3
column, and anything unregistered, so leakage fails loudly instead of quietly helping a metric.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal

import numpy as np
import pandas as pd
import yaml

from sg_data.defaults import fill_tier2
from sg_data.schema import BY_NAME, FIELDS, TIER2_INPUTS, fields
from sg_sim.config import SimConfig

Kind = Literal["numeric", "bool", "categorical"]
Group = Literal["input", "engineered", "calendar", "lag", "missing_flag", "outcome"]

CONFIG_DIR = Path(__file__).resolve().parents[2] / "configs"
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
# Lags look back at most this many calendar days for the previous workday (covers a weekend).
PREV_DAY_MAX_GAP = 4
TARGET = "ot_labor_hours"
# Column names as attributes (F.regular_patients), generated from the schema so formulas never
# re-list fields and a typo fails at import.
F = SimpleNamespace(**{f.name: f.name for f in FIELDS})


class LeakageError(ValueError):
    """A feature set asked for something not known at 7:00 AM."""


@dataclass(frozen=True)
class Feature:
    name: str
    kind: Kind
    group: Group
    known_at_7am: bool
    monotone: Literal[-1, 0, 1] = 0
    description: str = ""


def _schema_features() -> list[Feature]:
    out: list[Feature] = []
    for f in FIELDS:
        if f.role == "meta" or f.name == F.date:
            continue
        kind: Kind = (
            "categorical" if f.dtype == "enum" else "bool" if f.dtype == "bool" else "numeric"
        )
        if f.role == "outcome":
            out.append(Feature(f.name, kind, "outcome", False, 0, f.description))
        else:
            out.append(Feature(f.name, kind, "input", True, f.monotone, f.description))
    return out


ENGINEERED: tuple[Feature, ...] = (
    Feature(
        "total_afternoon_staff", "numeric", "engineered", True, -1, "Staff starting 11, 13, 15"
    ),
    Feature(
        "staff_hours_before_15",
        "numeric",
        "engineered",
        True,
        -1,
        "Staff hours on the floor before 3:00 PM",
    ),
    Feature(
        "patients_per_morning_staff",
        "numeric",
        "engineered",
        True,
        1,
        "Regular patients per morning staff member",
    ),
    Feature(
        "demand_units_est",
        "numeric",
        "engineered",
        True,
        1,
        "Expected work units from patients, MF cases and sessions",
    ),
    Feature(
        "capacity_ratio",
        "numeric",
        "engineered",
        True,
        1,
        "Expected work units per staff hour before 3:00 PM",
    ),
)
CALENDAR: tuple[Feature, ...] = (
    Feature("day_of_week", "categorical", "calendar", True, 0, "Weekday"),
    Feature("is_monday", "bool", "calendar", True, 0, "Monday"),
    Feature("is_friday", "bool", "calendar", True, 0, "Friday"),
    Feature("week_of_semester", "numeric", "calendar", True, 0, "Week of the academic term"),
)
LAGS: tuple[Feature, ...] = (
    Feature("ot_hours_prev_day", "numeric", "lag", True, 0, "Overtime on the previous workday"),
    Feature("ot_hours_7d_mean", "numeric", "lag", True, 0, "Mean overtime over the prior 7 days"),
)
MISSING_FLAGS: tuple[Feature, ...] = tuple(
    Feature(f"{n}__missing", "bool", "missing_flag", True, 0, f"{n} filled from defaults")
    for n in TIER2_INPUTS
)

REGISTRY: dict[str, Feature] = {
    f.name: f for f in (*_schema_features(), *ENGINEERED, *CALENDAR, *LAGS, *MISSING_FLAGS)
}

_TIER1_INPUTS = [f.name for f in fields(roles={"input"}, tiers={1}) if f.name != F.date]
_INPUTS = [n for n, f in REGISTRY.items() if f.group == "input"]

FEATURE_SETS: dict[str, tuple[str, ...]] = {
    "full": (
        *_INPUTS,
        *(f.name for f in ENGINEERED),
        *(f.name for f in CALENDAR),
        *(f.name for f in LAGS),
        *(f.name for f in MISSING_FLAGS),
    ),
    "core": (
        *_TIER1_INPUTS,
        *(f.name for f in CALENDAR),
        *(f.name for f in LAGS),
        "patients_per_morning_staff",
    ),
}

# Staffing features: adding one never raises predicted overtime (SG-17 monotonicity and SHAP
# direction gates use this list).
STAFFING = tuple(n for n, f in REGISTRY.items() if f.group == "input" and f.monotone == -1)


def check_features(names: Sequence[str]) -> list[Feature]:
    """Registry entries for names, or LeakageError if any is unsafe at 7:00 AM."""
    out: list[Feature] = []
    for name in names:
        feat = REGISTRY.get(name)
        if feat is None:
            raise LeakageError(f"{name} is not in the feature registry")
        spec = BY_NAME.get(name)
        if not feat.known_at_7am or (spec is not None and (spec.tier == 3 or spec.role != "input")):
            raise LeakageError(f"{name} is not known at 7:00 AM and cannot be a model input")
        out.append(feat)
    return out


def resolve_feature_set(feature_set: str | Sequence[str]) -> list[str]:
    if isinstance(feature_set, str):
        if feature_set not in FEATURE_SETS:
            raise ValueError(f"unknown feature set {feature_set!r}")
        return list(FEATURE_SETS[feature_set])
    return list(feature_set)


# ---------------------------------------------------------------------------
# Context: coefficients read from the calibrated simulator config, never hard-coded
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FeatureContext:
    units_per_patient: float
    units_per_mf_case: float
    units_per_session: float
    # Hours each start window works before 3:00 PM, keyed by shift_windows key.
    window_hours_before_15: dict[str, float]
    morning_hours_before_15: float
    outside_support_hours_before_15: float
    term_starts: tuple[str, ...]
    sim_config_hash: str

    @classmethod
    def from_config(cls, cfg: SimConfig, calendar_path: Path | None = None) -> FeatureContext:
        w, units = cfg.work, cfg.units
        end = cfg.clock.morning_end  # 3:00 PM, minutes after 7:00 AM

        def load(mix: dict[str, float]) -> float:
            return sum(rate * units[kind].weight for kind, rate in mix.items())

        cal = yaml.safe_load(
            (calendar_path or CONFIG_DIR / "academic_calendar.yaml").read_text(encoding="utf-8")
        )
        return cls(
            units_per_patient=load(w.per_patient) * cfg.scale.units_per_patient,
            units_per_mf_case=load(w.per_mf_case),
            # Issued session sets minus the expected unused share (known only after the shift).
            units_per_session=load(w.per_session)
            * cfg.scale.units_per_session
            * (1 - w.unused_share),
            window_hours_before_15={
                k: max(0.0, (end - start) / 60) for k, start in cfg.staff.starts.items()
            },
            morning_hours_before_15=end / 60,
            outside_support_hours_before_15=max(0.0, (end - cfg.staff.outside_support_start) / 60),
            term_starts=tuple(cal["term_starts"]),
            sim_config_hash=cfg.config_hash,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "units_per_patient": self.units_per_patient,
            "units_per_mf_case": self.units_per_mf_case,
            "units_per_session": self.units_per_session,
            "window_hours_before_15": self.window_hours_before_15,
            "morning_hours_before_15": self.morning_hours_before_15,
            "outside_support_hours_before_15": self.outside_support_hours_before_15,
            "term_starts": list(self.term_starts),
            "sim_config_hash": self.sim_config_hash,
        }


def week_of_semester(dates: pd.Series, term_starts: Sequence[str]) -> pd.Series:
    """1-based week since the most recent term start (previous year's last term in January)."""

    def one(d: dt.date) -> int:
        starts = [
            dt.date(y, int(md[:2]), int(md[3:])) for y in (d.year - 1, d.year) for md in term_starts
        ]
        last = max(s for s in starts if s <= d)
        return (d - last).days // 7 + 1

    return pd.Series([one(d) for d in pd.to_datetime(dates).dt.date], index=dates.index)


def sequence_ids(df: pd.DataFrame) -> pd.Series:
    """Group key for lags and splits. Simulated rows come in carryover-linked sequences laid out
    every SEQ_SPACING days from DESIGN_START (sg_sim.dataset); real rows form one sequence."""
    from sg_sim.dataset import DESIGN_START, SEQ_SPACING

    days = (pd.to_datetime(df[F.date]) - pd.Timestamp(DESIGN_START)).dt.days
    seq = days // SEQ_SPACING.days
    if "source" in df.columns:
        seq = seq.where(df["source"] == "simulated", -1)
    return pd.Series(seq.astype(int), index=df.index)


def add_lags(df: pd.DataFrame) -> pd.DataFrame:
    """ot_hours_prev_day and ot_hours_7d_mean from strictly earlier dates of the same department,
    source and sequence. Rows without a target (tomorrow's plan) get lags but never feed them."""
    out = df.copy()
    out["_seq"] = sequence_ids(out)
    keys = [c for c in ("department_id", "source", "_seq") if c in out.columns]
    out["_date"] = pd.to_datetime(out[F.date])
    out = out.sort_values([*keys, "_date"], kind="stable")
    prev = np.full(len(out), np.nan)
    mean7 = np.full(len(out), np.nan)
    pos = {idx: i for i, idx in enumerate(out.index)}
    target = out[TARGET] if TARGET in out.columns else pd.Series(np.nan, index=out.index)
    for _, g in out.groupby(keys, sort=False):
        dates = g["_date"].to_numpy()
        ys = target.loc[g.index].astype(float).to_numpy()
        for j, idx in enumerate(g.index):
            earlier = (dates < dates[j]) & ~np.isnan(ys)
            if not earlier.any():
                continue
            gap = (dates[j] - dates[earlier]) / np.timedelta64(1, "D")
            last = int(np.argmin(gap))
            if gap[last] <= PREV_DAY_MAX_GAP:
                prev[pos[idx]] = ys[earlier][last]
            window = gap <= 7
            if window.any():
                mean7[pos[idx]] = float(ys[earlier][window].mean())
    out["ot_hours_prev_day"] = prev
    out["ot_hours_7d_mean"] = mean7
    return out.drop(columns=["_seq", "_date"]).loc[df.index]


def add_features(
    df: pd.DataFrame,
    ctx: FeatureContext,
    settings: dict[str, Any] | None = None,
    *,
    lags: bool = True,
) -> pd.DataFrame:
    """Every registered derived column. Tier 2 gaps are filled (with __missing flags) from the
    department settings. With lags=False the caller supplies ot_hours_prev_day/_7d_mean."""
    out = df.copy()
    if not all(f"{n}__missing" in out.columns for n in TIER2_INPUTS):
        out = fill_tier2(out, settings or {})
    for n in TIER2_INPUTS:
        if BY_NAME[n].dtype in ("int", "float"):
            out[n] = pd.to_numeric(out[n])

    def num(col: str) -> pd.Series:
        return pd.Series(pd.to_numeric(out[col]), index=out.index, dtype=float)

    hrs = ctx.window_hours_before_15
    afternoon = [f"{k}_staff" for k in hrs]
    out["total_afternoon_staff"] = pd.concat([num(c) for c in afternoon], axis=1).sum(axis=1)
    out["staff_hours_before_15"] = (
        num(F.morning_staff_present) * ctx.morning_hours_before_15
        + pd.concat([num(f"{k}_staff") * h for k, h in hrs.items()], axis=1).sum(axis=1)
        + num(F.outside_support_staff) * ctx.outside_support_hours_before_15
    )
    out["patients_per_morning_staff"] = num(F.regular_patients) / num(F.morning_staff_present).clip(
        lower=1
    )
    out["demand_units_est"] = (
        num(F.regular_patients) * ctx.units_per_patient
        + num(F.mf_cases) * ctx.units_per_mf_case
        + num(F.student_clinic_sessions) * ctx.units_per_session
    )
    out["capacity_ratio"] = out["demand_units_est"] / out["staff_hours_before_15"].clip(lower=1)
    dates = pd.to_datetime(out[F.date])
    out["day_of_week"] = [WEEKDAYS[d] for d in dates.dt.day_of_week]
    out["is_monday"] = dates.dt.day_of_week == 0
    out["is_friday"] = dates.dt.day_of_week == 4
    out["week_of_semester"] = week_of_semester(out[F.date], ctx.term_starts)
    if lags:
        out = add_lags(out)
    return out


def build_matrix(df: pd.DataFrame, feature_set: str | Sequence[str]) -> pd.DataFrame:
    """The model input frame: exactly the registered, 7:00 AM-safe columns of a feature set, in
    registry types (bools and numbers as float, categoricals as str)."""
    names = resolve_feature_set(feature_set)
    feats = check_features(names)
    missing = [n for n in names if n not in df.columns]
    if missing:
        raise KeyError(f"columns missing from the frame (run add_features first): {missing}")
    out = pd.DataFrame(index=df.index)
    for f in feats:
        col = df[f.name]
        if f.kind == "categorical":
            out[f.name] = col.astype(str)
        else:
            out[f.name] = pd.to_numeric(col.astype(object), errors="coerce").astype(float)
    return out


def monotone_constraints(names: Sequence[str]) -> dict[str, int]:
    return {n: REGISTRY[n].monotone for n in names}


def categorical(names: Sequence[str]) -> list[str]:
    return [n for n in names if REGISTRY[n].kind == "categorical"]
