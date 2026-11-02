"""Staffing scenario engine (SG-19, plan §12.6).

Given tomorrow's plan, evaluate every staffing option inside the lever bounds in one vectorized
call per model, and return the options, their Pareto front on (added staff-hours, predicted
overtime) and the smallest change that meets the department's target.

Two rules keep the recommendation honest (ADR-0008):
- Options with staffing outside what the model saw in training are flagged low_confidence and
  never recommended.
- "Staff willing to stay" is a what-if, not a staffing change: fewer volunteers lowers predicted
  overtime only because work is left for tomorrow. Options that change it can be explored but
  are never recommended and are left off the Pareto front.

Every result is a model estimate, not a guarantee.
"""

from __future__ import annotations

import itertools
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

import numpy as np
import pandas as pd

from sg_ml.features import F, FeatureContext, add_features, build_matrix
from sg_ml.models import CLASSES, combine_quantiles

DISCLAIMER = "Model estimate, not a guarantee."
# Levers in display order. Staff levers add people; the volunteer lever is a what-if.
STAFF_LEVERS: tuple[str, ...] = (
    F.morning_staff_present,
    F.aft_11_staff,
    F.aft_13_staff,
    F.outside_support_staff,
)
VOLUNTEER_LEVER: str = F.ot_available_staff
LEVERS: tuple[str, ...] = (*STAFF_LEVERS, VOLUNTEER_LEVER)
# Shift window key for each start-time lever (department settings shift_windows).
WINDOW_KEYS = {
    F.morning_staff_present: "morning",
    F.aft_11_staff: "aft_11",
    F.aft_13_staff: "aft_13",
}
DEFAULT_MAX_ADD = 2
MAX_OPTIONS = 500
# Added staff count until 15:00 (the morning overtime period); outside support until it leaves.
CUTOFF = "15:00"
OUTSIDE_SUPPORT_UNTIL = "20:00"

TargetType = Literal["p50_hours", "p_high"]


class ScenarioError(ValueError):
    """Bad lever bounds or target (the API maps this to 422)."""


@dataclass(frozen=True)
class Target:
    type: TargetType
    value: float

    def met(self, p50: np.ndarray, p_high: np.ndarray) -> np.ndarray:
        return (p50 if self.type == "p50_hours" else p_high) <= self.value + 1e-9


@dataclass(frozen=True)
class Option:
    id: str
    values: dict[str, int]
    changes: dict[str, int]
    ot_p10: float
    ot_p50: float
    ot_p90: float
    burden_probs: dict[str, float]
    added_staff_hours: float
    meets_target: bool
    low_confidence: bool
    what_if: bool


@dataclass
class ScenarioResult:
    base: Option
    options: list[Option]
    pareto_ids: list[str]
    minimum_change_id: str | None
    target: Target
    message: str
    model_version: str
    bounds: dict[str, tuple[int, int]]
    window_hours: dict[str, float]
    support: dict[str, tuple[float, float]] = field(default_factory=dict)
    disclaimer: str = DISCLAIMER

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["bounds"] = {k: list(v) for k, v in self.bounds.items()}
        out["support"] = {k: list(v) for k, v in self.support.items()}
        return out

    def option(self, option_id: str) -> Option | None:
        return next((o for o in self.options if o.id == option_id), None)


def _hours(hhmm: str) -> float:
    h, m = hhmm.split(":")
    return int(h) + int(m) / 60


def window_hours(settings: Mapping[str, Any], ctx: FeatureContext) -> dict[str, float]:
    """Working hours one added person contributes per lever: until 15:00 for the morning and
    afternoon start windows, until outside_support_until for outside support. Start times come
    from department settings, falling back to the model's training context."""
    windows = {
        str(w.get("key")): w
        for w in settings.get("shift_windows") or []
        if isinstance(w, dict) and w.get("start")
    }
    cutoff = _hours(CUTOFF)
    out: dict[str, float] = {}
    for lever, key in WINDOW_KEYS.items():
        if key in windows:
            out[lever] = max(0.0, cutoff - _hours(str(windows[key]["start"])))
        elif key == "morning":
            out[lever] = ctx.morning_hours_before_15
        else:
            out[lever] = ctx.window_hours_before_15.get(key, 0.0)
    start = cutoff - ctx.outside_support_hours_before_15
    until = _hours(str(settings.get("outside_support_until") or OUTSIDE_SUPPORT_UNTIL))
    out[F.outside_support_staff] = max(0.0, until - start)
    out[VOLUNTEER_LEVER] = 0.0
    return out


def default_bounds(base: Mapping[str, Any]) -> dict[str, tuple[int, int]]:
    """+0 to +2 people per staff lever; volunteers from 0 to the morning staff count."""
    out = {k: (int(base[k]), int(base[k]) + DEFAULT_MAX_ADD) for k in STAFF_LEVERS}
    out[VOLUNTEER_LEVER] = (0, int(base[F.morning_staff_present]))
    return out


def resolve_bounds(
    base: Mapping[str, Any], overrides: Mapping[str, Mapping[str, int]] | None
) -> dict[str, tuple[int, int]]:
    bounds = default_bounds(base)
    for lever, b in (overrides or {}).items():
        if lever not in bounds:
            raise ScenarioError(f"{lever} is not a staffing lever")
        lo, hi = int(b.get("min", bounds[lever][0])), int(b.get("max", bounds[lever][1]))
        if lo < 0 or hi < lo:
            raise ScenarioError(f"{lever}: bounds must satisfy 0 <= min <= max")
        bounds[lever] = (lo, hi)
    size = int(np.prod([hi - lo + 1 for lo, hi in bounds.values()]))
    if size > MAX_OPTIONS:
        raise ScenarioError(f"{size} options exceed the limit of {MAX_OPTIONS}; narrow the bounds")
    return bounds


def default_target(settings: Mapping[str, Any], thresholds: list[float]) -> Target:
    """The department's alert threshold if set, otherwise the top of the Moderate class."""
    alert = settings.get("alert_threshold_hours")
    return Target("p50_hours", float(alert if alert is not None else thresholds[1]))


def support_from_artifact(artifact: Mapping[str, Any]) -> dict[str, tuple[float, float]]:
    """Training min and max per lever. New artifacts store them (staffing_support); older ones
    fall back to the saved explainer background, a training sample whose range is narrower, so
    the check errs toward flagging (ADR-0008)."""
    stored = artifact.get("staffing_support")
    if stored:
        return {k: (float(v[0]), float(v[1])) for k, v in stored.items() if k in LEVERS}
    bg = artifact.get("explainer_background")
    if isinstance(bg, pd.DataFrame):
        return {
            k: (float(bg[k].min()), float(bg[k].max()))
            for k in LEVERS
            if k in bg.columns and bg[k].notna().any()
        }
    return {}


def staffing_support(frame: pd.DataFrame) -> dict[str, list[float]]:
    """What train() stores: the min and max of each lever over the training rows."""
    return {
        k: [float(frame[k].min()), float(frame[k].max())]
        for k in LEVERS
        if k in frame.columns and frame[k].notna().any()
    }


def grid(bounds: Mapping[str, tuple[int, int]], base: Mapping[str, Any]) -> pd.DataFrame:
    """Every lever combination; volunteers never exceed that option's morning staff."""
    ranges = [range(bounds[k][0], bounds[k][1] + 1) for k in LEVERS]
    combos = pd.DataFrame(list(itertools.product(*ranges)), columns=list(LEVERS))
    combos = combos[combos[VOLUNTEER_LEVER] <= combos[F.morning_staff_present]]
    base_values = {k: int(base[k]) for k in LEVERS}
    # The base plan is always evaluated, even when the bounds leave it out.
    is_base = (combos[list(LEVERS)] == pd.Series(base_values)).all(axis=1)
    if not is_base.any():
        combos = pd.concat([pd.DataFrame([base_values]), combos], ignore_index=True)
    out: pd.DataFrame = combos.reset_index(drop=True)
    return out


def option_id(changes: Mapping[str, int], values: Mapping[str, int]) -> str:
    """Stable, readable id from the staff deltas and the volunteer count:
    m+0.a11+1.a13+0.os+0.v2"""
    tags = {
        F.morning_staff_present: "m",
        F.aft_11_staff: "a11",
        F.aft_13_staff: "a13",
        F.outside_support_staff: "os",
    }
    parts = [f"{tags[k]}{changes[k]:+d}" for k in STAFF_LEVERS]
    return ".".join([*parts, f"v{values[VOLUNTEER_LEVER]}"])


def predict_frame(artifact: Mapping[str, Any], X: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """(n, 3) p10/p50/p90 band and (n, 3) class probabilities in CLASSES order: one predict call
    per model for the whole grid."""
    names = list(artifact["feature_list"])
    band = combine_quantiles([artifact[f"pipeline_p{q}"].predict(X[names]) for q in (10, 50, 90)])
    clf = artifact["classifier"]
    raw = clf.predict_proba(X[names])
    probs = np.zeros((len(X), len(CLASSES)))
    for j, c in enumerate(clf.classes_):
        probs[:, CLASSES.index(str(c))] = raw[:, j]
    return band, probs


def pareto(ids: list[str], cost: np.ndarray, p50: np.ndarray) -> list[str]:
    """Options no other option beats on both added staff-hours and p50 (ties kept once)."""
    order = np.lexsort((p50, cost))
    out: list[str] = []
    best = np.inf
    for i in order:
        if p50[i] < best - 1e-9:
            out.append(ids[i])
            best = p50[i]
    return out


def evaluate(
    artifact: Mapping[str, Any],
    base_row: Mapping[str, Any],
    settings: Mapping[str, Any],
    *,
    model_version: str,
    levers: Mapping[str, Mapping[str, int]] | None = None,
    target: Target | None = None,
) -> ScenarioResult:
    """Run the engine on one plan row. base_row holds the plan inputs, the __missing flags, the
    date and the two lag features (already computed from approved actuals)."""
    ctx = FeatureContext.from_dict(artifact["context"])
    for k in LEVERS:
        if base_row.get(k) is None:
            raise ScenarioError(f"the plan has no value for {k}")
    bounds = resolve_bounds(base_row, levers)
    target = target or default_target(settings, list(artifact["thresholds"]))
    hours = window_hours(settings, ctx)
    support = support_from_artifact(artifact)

    combos = grid(bounds, base_row)
    raw = pd.DataFrame([dict(base_row)] * len(combos))
    for k in LEVERS:
        raw[k] = combos[k].to_numpy()
    frame = add_features(raw, ctx, dict(settings), lags=False)
    X = build_matrix(frame, list(artifact["feature_list"]))
    band, probs = predict_frame(artifact, X)

    base_vals = np.array([int(base_row[k]) for k in LEVERS])
    values = combos[list(LEVERS)].to_numpy(dtype=int)
    deltas = values - base_vals
    added = np.zeros(len(combos))
    for j, k in enumerate(STAFF_LEVERS):
        added += np.clip(deltas[:, j], 0, None) * hours[k]
    p_high = probs[:, CLASSES.index("high")]
    meets = target.met(band[:, 1], p_high)
    low_conf = np.zeros(len(combos), dtype=bool)
    for j, k in enumerate(LEVERS):
        if k in support:
            lo, hi = support[k]
            low_conf |= (values[:, j] < lo) | (values[:, j] > hi)
    what_if = deltas[:, -1] != 0

    options: list[Option] = []
    for i in range(len(combos)):
        vals = {k: int(values[i, j]) for j, k in enumerate(LEVERS)}
        changes = {k: int(deltas[i, j]) for j, k in enumerate(LEVERS)}
        options.append(
            Option(
                id=option_id(changes, vals),
                values=vals,
                changes=changes,
                ot_p10=round(float(band[i, 0]), 2),
                ot_p50=round(float(band[i, 1]), 2),
                ot_p90=round(float(band[i, 2]), 2),
                burden_probs={c: round(float(probs[i, k]), 4) for k, c in enumerate(CLASSES)},
                added_staff_hours=round(float(added[i]), 2),
                meets_target=bool(meets[i]),
                low_confidence=bool(low_conf[i]),
                what_if=bool(what_if[i]),
            )
        )
    ids = [o.id for o in options]
    base_idx = int(np.flatnonzero((deltas == 0).all(axis=1))[0])

    eligible = ~low_conf & ~what_if
    elig_idx = np.flatnonzero(eligible)
    front = pareto([ids[i] for i in elig_idx], added[elig_idx], band[elig_idx, 1])
    feasible = np.flatnonzero(eligible & meets)
    minimum: str | None = None
    if len(feasible):
        # Least added staff-hours; ties go to the lower p90, then the lower p50.
        best = feasible[np.lexsort((band[feasible, 1], band[feasible, 2], added[feasible]))[0]]
        minimum = ids[best]
    message = _message(options[base_idx], options, minimum, target, bounds)
    return ScenarioResult(
        base=options[base_idx],
        options=options,
        pareto_ids=front,
        minimum_change_id=minimum,
        target=target,
        message=message,
        model_version=model_version,
        bounds=bounds,
        window_hours=hours,
        support=support,
    )


LABELS = {
    F.morning_staff_present: "staff starting at 7:00",
    F.aft_11_staff: "staff starting at 11:00",
    F.aft_13_staff: "staff starting at 13:00",
    F.outside_support_staff: "outside support staff",
}


def describe_changes(changes: Mapping[str, int]) -> str:
    """'Add 1 staff starting at 11:00 and 1 outside support staff' (staff levers only)."""
    parts = [f"{n} {LABELS[k]}" for k in STAFF_LEVERS if (n := changes.get(k, 0)) > 0]
    if not parts:
        return "Keep the plan as it is"
    if len(parts) == 1:
        return f"Add {parts[0]}"
    return f"Add {', '.join(parts[:-1])} and {parts[-1]}"


def _message(
    base: Option,
    options: list[Option],
    minimum: str | None,
    target: Target,
    bounds: Mapping[str, tuple[int, int]],
) -> str:
    if minimum is None:
        top = [f"+{bounds[k][1] - base.values[k]}" for k in STAFF_LEVERS]
        if len(set(top)) == 1:
            reach = f"{top[0]} staff in every window"
        else:
            reach = "the most staff the bounds allow"
        return f"Even with {reach}, predicted overtime stays above the target."
    best = next(o for o in options if o.id == minimum)
    if best.id == base.id:
        return f"Tomorrow's plan already meets the target ({_target_text(target)})."
    return (
        f"{describe_changes(best.changes)}. Predicted overtime drops from "
        f"{base.ot_p50:g} to {best.ot_p50:g} hours (most likely)."
    )


def _target_text(target: Target) -> str:
    if target.type == "p50_hours":
        return f"at most {target.value:g} overtime hours"
    return f"high-burden probability at most {target.value:.0%}"
