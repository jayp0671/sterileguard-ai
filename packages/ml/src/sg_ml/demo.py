"""Demo history for the demo organization (SG-16): the last N workdays simulated from the
calibrated model (source = simulated) and forecasts from a model artifact, all deterministic so
`sg demo reset-demo` reproduces exactly the same state. Synthetic only.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

import numpy as np
import pandas as pd

from sg_ml import driver_text
from sg_ml.explain import Explainer
from sg_ml.features import TARGET, F, FeatureContext, add_features, build_matrix
from sg_ml.models import CLASSES, combine_quantiles
from sg_sim.config import SimConfig

DEMO_SEED = 2026
NAMESPACE = uuid.UUID("5e1e7c1a-6d0a-4b7e-9a8f-0d3e5a1c2b4f")


def demo_id(*parts: object) -> str:
    """Stable ids so a reset reproduces identical rows."""
    return str(uuid.uuid5(NAMESPACE, ":".join(str(p) for p in parts)))


def demo_workdays(today: dt.date, days: int) -> list[dt.date]:
    """Workdays in the `days` calendar days before today, oldest first."""
    out = [today - dt.timedelta(days=k) for k in range(days, 0, -1)]
    return [d for d in out if d.weekday() < 5]


def staffing_for(day: dt.date, rng: np.random.Generator) -> dict[str, int]:
    """Department-default staffing with the day-to-day variation a real schedule has."""
    morning = int(rng.choice([3, 3, 3, 2, 4]))
    return {
        F.morning_staff_present: morning,
        F.aft_11_staff: int(rng.choice([3, 3, 2, 4])),
        F.aft_13_staff: int(rng.choice([1, 1, 0, 2])),
        F.aft_15_staff: 2,
        F.outside_support_staff: int(rng.choice([2, 2, 1])),
        F.ot_available_staff: min(morning, int(rng.choice([2, 2, 1, 3]))),
        F.washers_up: int(rng.choice([2] * 9 + [1])),
        F.sterilizers_up: int(rng.choice([2] * 8 + [1])),
    }


def history(
    cfg: SimConfig, today: dt.date, department_id: str, days: int = 90, seed: int = DEMO_SEED
) -> pd.DataFrame:
    """One carryover-linked simulated sequence over the demo window, as schema rows."""
    from sg_sim.export import result_row, to_frame
    from sg_sim.run import backlog_scale, simulate_day
    from sg_sim.sampler import sample_inputs

    rng = np.random.default_rng(seed)
    carry = None
    rows: list[dict[str, Any]] = []
    for d in demo_workdays(today, days):
        backlog = backlog_scale(len(carry), cfg) if carry is not None else 1
        inputs = sample_inputs(
            d, cfg, rng, staffing=staffing_for(d, rng), carryover_estimate=backlog
        )
        result = simulate_day(inputs, cfg, rng, carryover=carry)
        rows.append(result_row(result))
        carry = result.carryover[: cfg.work.max_carryover_units]
    return to_frame(rows, department_id, demo_id("dataset", department_id))


def forecasts(
    df: pd.DataFrame,
    artifact: dict[str, Any],
    version: str,
    created_by: str | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """A 'scheduled' forecast for every demo day (made the evening before, so lags use only
    earlier days), with SHAP drivers. Returns (forecast rows, driver rows)."""
    ctx = FeatureContext.from_dict(artifact["context"])
    frame = add_features(df, ctx)
    X = build_matrix(frame, artifact["feature_list"])
    band = combine_quantiles([artifact[f"pipeline_p{q}"].predict(X) for q in (10, 50, 90)])
    clf = artifact["classifier"]
    proba = clf.predict_proba(X)
    explainer = Explainer(artifact["pipeline_p50"], artifact["feature_list"])
    thresholds = {
        "low_max": artifact["thresholds"][0],
        "moderate_max": artifact["thresholds"][1],
        "source": artifact.get("thresholds_source", "simulated_provisional"),
    }
    out: list[dict[str, Any]] = []
    drivers: list[dict[str, Any]] = []
    for i, (_, row) in enumerate(frame.iterrows()):
        day = pd.Timestamp(row["date"]).date()
        fid = demo_id("forecast", row["department_id"], day.isoformat())
        probs = {str(c): float(p) for c, p in zip(clf.classes_, proba[i], strict=True)}
        probs = {c: round(probs.get(c, 0.0), 4) for c in CLASSES}
        evening_before = dt.datetime.combine(day - dt.timedelta(days=1), dt.time(22, 0), dt.UTC)
        out.append(
            {
                "id": fid,
                "department_id": row["department_id"],
                "target_date": day.isoformat(),
                "plan_id": demo_id("plan", row["department_id"], day.isoformat()),
                "model_version": version,
                "feature_set": artifact["feature_set"],
                "ot_p10": round(float(band[i, 0]), 2),
                "ot_p50": round(float(band[i, 1]), 2),
                "ot_p90": round(float(band[i, 2]), 2),
                "burden_class": max(probs, key=lambda c: probs[c]),
                "burden_probs": probs,
                "thresholds": thresholds,
                "trigger": "scheduled",
                "created_by": created_by,
                "created_at": evening_before.isoformat(),
            }
        )
        for d in explainer.explain(X.iloc[[i]]).drivers:
            key, params, text = driver_text.sentence(d.feature, d.value, d.contribution_hours)
            drivers.append(
                {
                    "forecast_id": fid,
                    "rank": d.rank,
                    "feature": d.feature,
                    "value": None
                    if d.value is None
                    else driver_text.display_value(d.feature, d.value),
                    "contribution_hours": round(d.contribution_hours, 3),
                    "text_key": key,
                    "text_params": params,
                    "default_text": text,
                }
            )
    return out, drivers


def summary(df: pd.DataFrame) -> dict[str, Any]:
    return {
        "days": len(df),
        "first": pd.Timestamp(df["date"].min()).date().isoformat(),
        "last": pd.Timestamp(df["date"].max()).date().isoformat(),
        "ot_mean": round(float(df[TARGET].mean()), 2),
    }
