"""Activation gates (SG-17, plan §12.4). A model version can be activated only when every
required gate passes; `sg ml evaluate --run` writes the results into the run and its model card.

Gates work on the run's own time-ordered holdout, rebuilt from the training dataset with the
artifact's feature context, so they test exactly what would be served.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

from sg_data.schema import BY_NAME
from sg_ml.explain import Explainer
from sg_ml.features import (
    STAFFING,
    TARGET,
    FeatureContext,
    LeakageError,
    add_features,
    build_matrix,
    check_features,
)
from sg_ml.models import hgb_regressor
from sg_ml.train import time_split

MAE_RATIO_MAX = 0.85
COVERAGE_RANGE = (0.75, 0.85)
MONOTONE_ROWS = 200
DETERMINISM_ROWS = 50
REAL_DAYS_REQUIRED = 10
TOLERANCE = 1e-9


@dataclass(frozen=True)
class GateResult:
    name: str
    required: bool
    passed: bool
    value: Any
    threshold: Any
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def beats_baselines(run: dict[str, Any]) -> GateResult:
    reg = run["metrics"]["regression"]
    model = reg["hgb_p50"]["mae"]
    best_name = min((k for k in reg if k.startswith("baseline_")), key=lambda k: reg[k]["mae"])
    best = reg[best_name]["mae"]
    ratio = model / best if best > 0 else float("inf")
    return GateResult(
        "beats_baselines",
        True,
        ratio <= MAE_RATIO_MAX,
        round(ratio, 4),
        MAE_RATIO_MAX,
        f"MAE {model:.3f} vs best baseline {best_name} {best:.3f}",
    )


def interval_coverage(run: dict[str, Any]) -> GateResult:
    cov = run["metrics"]["regression"]["hgb_p50"]["coverage_80"]
    lo, hi = COVERAGE_RANGE
    return GateResult(
        "interval_coverage",
        True,
        lo <= cov <= hi,
        cov,
        [lo, hi],
        f"80% band covers {cov:.1%} of holdout days",
    )


def no_leakage(features: Sequence[str]) -> GateResult:
    try:
        check_features(features)
    except LeakageError as exc:
        return GateResult("no_leakage", True, False, str(exc), "known_at_7am", str(exc))
    unsafe = [
        f for f in features if f in BY_NAME and (BY_NAME[f].tier == 3 or BY_NAME[f].role != "input")
    ]
    return GateResult(
        "no_leakage",
        True,
        not unsafe,
        unsafe,
        "known_at_7am",
        "every feature is known at 7:00 AM" if not unsafe else f"unsafe: {unsafe}",
    )


def _p50(artifact: dict[str, Any], F: pd.DataFrame) -> np.ndarray:
    raw = artifact["pipeline_p50"].predict(build_matrix(F, artifact["feature_list"]))
    return np.clip(np.asarray(raw, dtype=float), 0, None)


def monotonicity(
    artifact: dict[str, Any], F: pd.DataFrame, ctx: FeatureContext, seed: int = 0
) -> GateResult:
    """+1 to any staffing input (engineered features recomputed) never raises p50, and one
    sterilizer fewer never lowers it."""
    rows = F.sample(min(MONOTONE_ROWS, len(F)), random_state=seed).reset_index(drop=True)
    base = _p50(artifact, rows)
    worst, where = 0.0, ""
    for feat in STAFFING:
        bumped = rows.copy()
        bumped[feat] = pd.to_numeric(bumped[feat]) + 1
        rise = float((_p50(artifact, add_features(bumped, ctx, lags=False)) - base).max())
        if rise > worst:
            worst, where = rise, f"+1 {feat}"
    has = pd.to_numeric(rows["sterilizers_up"]) >= 1
    fewer = rows[has].copy()
    fewer["sterilizers_up"] = pd.to_numeric(fewer["sterilizers_up"]) - 1
    if len(fewer):
        drop = float(
            (base[has.to_numpy()] - _p50(artifact, add_features(fewer, ctx, lags=False))).max()
        )
        if drop > worst:
            worst, where = drop, "-1 sterilizer lowered p50"
    return GateResult(
        "monotonicity",
        True,
        worst <= TOLERANCE,
        round(worst, 6),
        0,
        f"worst violation {worst:.4f} h ({where})" if where else "no violations",
    )


def shap_direction(artifact: dict[str, Any], X: pd.DataFrame) -> GateResult:
    """Slope of each staffing feature's SHAP value against its value must be <= 0 (ADR-0006)."""
    check = Explainer(artifact["pipeline_p50"], artifact["feature_list"]).direction_check(X)
    worst_feat = max(check, key=lambda f: check[f]["slope"])
    worst = check[worst_feat]["slope"]
    return GateResult(
        "shap_direction",
        True,
        worst <= TOLERANCE,
        {f: v["slope"] for f, v in check.items()},
        0,
        f"largest SHAP slope {worst:+.4f} h per unit ({worst_feat})",
    )


def determinism(
    artifact: dict[str, Any], F_train: pd.DataFrame, F_check: pd.DataFrame
) -> GateResult:
    names = artifact["feature_list"]
    again = hgb_regressor(names, artifact["params"], artifact["seed"]).fit(
        build_matrix(F_train, names), F_train[TARGET].astype(float)
    )
    rows = F_check.head(DETERMINISM_ROWS)
    a = artifact["pipeline_p50"].predict(build_matrix(rows, names))
    b = again.predict(build_matrix(rows, names))
    diff = float(np.abs(np.asarray(a) - np.asarray(b)).max())
    return GateResult(
        "determinism",
        True,
        diff == 0.0,
        diff,
        0,
        f"retrained with seed {artifact['seed']}: max difference {diff:g} h on {len(rows)} rows",
    )


def classifier_calibration(run: dict[str, Any]) -> GateResult:
    clf = run["metrics"]["classification"]
    model = clf["hgb_classifier"]["brier"]
    base = clf["baseline_logistic"]["brier"]
    return GateResult(
        "classifier_calibration",
        True,
        model <= base,
        model,
        base,
        f"Brier {model:.3f} vs logistic baseline {base:.3f}",
    )


def real_data_check(real_mae: float | None, real_days: int) -> GateResult:
    """Reported, not required until SG-29."""
    if real_days < REAL_DAYS_REQUIRED or real_mae is None:
        msg = f"{real_days} real test days; needs {REAL_DAYS_REQUIRED} before it is measured"
        return GateResult("real_data_check", False, False, None, REAL_DAYS_REQUIRED, msg)
    return GateResult(
        "real_data_check",
        False,
        True,
        round(real_mae, 4),
        None,
        f"MAE {real_mae:.3f} h on {real_days} real days",
    )


def run_gates(
    run: dict[str, Any],
    artifact: dict[str, Any],
    df: pd.DataFrame,
    *,
    real_mae: float | None = None,
    real_days: int = 0,
) -> list[GateResult]:
    ctx = FeatureContext.from_dict(artifact["context"])
    F = add_features(df, ctx).reset_index(drop=True)
    F = F[F[TARGET].notna()].reset_index(drop=True)
    tr, ho, _ = time_split(F)
    holdout = F[ho].reset_index(drop=True)
    X_ho = build_matrix(holdout, artifact["feature_list"])
    return [
        beats_baselines(run),
        interval_coverage(run),
        no_leakage(artifact["feature_list"]),
        monotonicity(artifact, holdout, ctx),
        shap_direction(artifact, X_ho.iloc[:: max(1, len(X_ho) // 500)]),
        determinism(artifact, F[tr].reset_index(drop=True), holdout),
        classifier_calibration(run),
        real_data_check(real_mae, real_days),
    ]


def passed(results: Sequence[GateResult]) -> bool:
    return all(r.passed for r in results if r.required)


def table(results: Sequence[GateResult]) -> str:
    lines = ["| Gate | Required | Result | Value | Detail |", "| --- | --- | --- | --- | --- |"]
    for r in results:
        result = "pass" if r.passed else ("FAIL" if r.required else "not met")
        value = r.value if not isinstance(r.value, dict) else max(r.value.values())
        lines.append(
            f"| {r.name} | {'yes' if r.required else 'no'} | {result} | {value} | {r.message} |"
        )
    return "\n".join(lines)
