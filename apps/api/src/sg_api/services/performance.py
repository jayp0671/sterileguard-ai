"""Model performance (SG-24 Part B, plan §12.7).

Two views of accuracy:
- holdout: the simulated holdout metrics stored in each active model's card at training time;
- live: the department's forecasts joined with approved *real* shift actuals in a window.
  Per day the latest forecast for that date counts. Simulated actuals (demo history) never
  count as real-world accuracy.

The burden confusion matrix appears only once thresholds come from real data (SG-29); with
provisional simulated cutoffs it would describe the simulator, not the department.
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Iterable, Mapping
from typing import Any

CLASSES = ("low", "moderate", "high")
HIST_BINS = 10
COVERAGE_TARGET = 0.8


def _f(v: Any) -> float | None:
    if v is None:
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def latest_per_day(forecasts: Iterable[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    out: dict[str, Mapping[str, Any]] = {}
    for f in forecasts:
        day = str(f["target_date"])
        if day not in out or str(f["created_at"]) > str(out[day]["created_at"]):
            out[day] = f
    return out


def burden(hours: float, thresholds: Mapping[str, Any]) -> str:
    low, moderate = _f(thresholds.get("low_max")), _f(thresholds.get("moderate_max"))
    if low is None or moderate is None:
        return "moderate"
    return "low" if hours <= low else "moderate" if hours <= moderate else "high"


def histogram(values: list[float], bins: int = HIST_BINS) -> list[dict[str, float | int]]:
    if not values:
        return []
    lo, hi = min(values), max(values)
    if lo == hi:
        return [{"start": round(lo, 2), "end": round(hi, 2), "count": len(values)}]
    width = (hi - lo) / bins
    counts = [0] * bins
    for v in values:
        counts[min(int((v - lo) / width), bins - 1)] += 1
    return [
        {"start": round(lo + i * width, 2), "end": round(lo + (i + 1) * width, 2), "count": c}
        for i, c in enumerate(counts)
    ]


def live_metrics(
    forecasts: Iterable[Mapping[str, Any]],
    actuals: Iterable[Mapping[str, Any]],
    window: int,
) -> dict[str, Any]:
    by_day = latest_per_day(forecasts)
    real = {
        str(a["shift_date"]): _f(a["ot_labor_hours"])
        for a in actuals
        if a.get("source") == "real" and a.get("status") == "approved"
    }
    daily: list[dict[str, Any]] = []
    for day in sorted(set(by_day) & set(real)):
        f, actual = by_day[day], real[day]
        p10, p50, p90 = _f(f.get("ot_p10")), _f(f.get("ot_p50")), _f(f.get("ot_p90"))
        if actual is None or p50 is None or p10 is None or p90 is None:
            continue
        daily.append(
            {
                "date": day,
                "p10": p10,
                "p50": p50,
                "p90": p90,
                "actual": actual,
                "error": round(actual - p50, 3),
                "covered": p10 <= actual <= p90,
                "predicted_class": f.get("burden_class"),
                "thresholds": f.get("thresholds") or {},
            }
        )
    n = len(daily)
    out: dict[str, Any] = {
        "window_days": window,
        "days": n,
        "mae": None,
        "rmse": None,
        "coverage_80": None,
        "coverage_target": COVERAGE_TARGET,
        "bias": None,
        "daily": [{k: v for k, v in d.items() if k != "thresholds"} for d in daily],
        "residual_histogram": [],
        "confusion": None,
    }
    if not n:
        return out
    errs = [d["error"] for d in daily]
    out.update(
        mae=round(sum(abs(e) for e in errs) / n, 3),
        rmse=round(math.sqrt(sum(e * e for e in errs) / n), 3),
        coverage_80=round(sum(d["covered"] for d in daily) / n, 3),
        bias=round(sum(errs) / n, 3),
        residual_histogram=histogram(errs),
    )
    real_cut = [d for d in daily if d["thresholds"].get("source") == "real"]
    if real_cut:
        matrix = [[0] * len(CLASSES) for _ in CLASSES]
        for d in real_cut:
            pred = d["predicted_class"] if d["predicted_class"] in CLASSES else "moderate"
            act = burden(d["actual"], d["thresholds"])
            matrix[CLASSES.index(act)][CLASSES.index(pred)] += 1
        out["confusion"] = {"labels": list(CLASSES), "matrix": matrix, "days": len(real_cut)}
    return out


def card_view(row: Mapping[str, Any]) -> dict[str, Any]:
    """One registered version as the page shows it: holdout metrics and the readable card."""
    card = dict(row.get("card") or {})
    metrics = dict(row.get("metrics") or card.get("metrics") or {})
    fs = row.get("feature_set", "full")
    feature_sets = dict(metrics.get("feature_sets") or {})
    holdout = dict(feature_sets.get(fs) or (metrics.get("regression") or {}).get("hgb_p50") or {})
    gates = [
        {k: g.get(k) for k in ("name", "passed", "required", "message")}
        for g in card.get("gates") or []
    ]
    return {
        "version": row["version"],
        "feature_set": fs,
        "status": row.get("status"),
        "gates_passed": bool(row.get("gates_passed")),
        "created_at": row.get("created_at"),
        "activated_at": row.get("activated_at"),
        # Only a platform admin (API) or the sg CLI (service role, no user) can activate.
        "activated_by_role": (
            "platform_admin"
            if row.get("activated_by")
            else ("cli" if row.get("activated_at") else None)
        ),
        "datasets": list(card.get("datasets") or []),
        "thresholds": card.get("thresholds"),
        "thresholds_source": card.get("thresholds_source") or "simulated_provisional",
        "holdout": {
            "mae": _f(holdout.get("mae")),
            "rmse": _f(holdout.get("rmse")),
            "coverage_80": _f(holdout.get("coverage_80")),
            "mean_width_80": _f(holdout.get("mean_width_80")),
        },
        "feature_sets": {
            k: {m: _f(v.get(m)) for m in ("mae", "rmse", "coverage_80", "mean_width_80")}
            for k, v in feature_sets.items()
            if isinstance(v, dict)
        },
        "baselines": {
            k: _f(v.get("mae"))
            for k, v in (metrics.get("regression") or {}).items()
            if isinstance(v, dict) and k.startswith("baseline")
        },
        "shap_global": [
            {"feature": s.get("feature"), "mean_abs_shap": _f(s.get("mean_abs_shap"))}
            for s in card.get("shap_global_top10") or []
        ],
        "card": {
            "intended_use": card.get("intended_use"),
            "limitations": list(card.get("limitations") or []),
            "features": list(card.get("features") or []),
            "run_id": card.get("run_id"),
            "trained_at": card.get("created_at"),
            "gates": gates,
        },
    }


def window_start(today: dt.date, window: int) -> dt.date:
    return today - dt.timedelta(days=window)
