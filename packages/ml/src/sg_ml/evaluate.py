"""Evaluation metrics and the run report (SG-13, plan §12.4)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
from sklearn.metrics import (
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
    roc_auc_score,
)

from sg_ml.models import CLASSES, QUANTILES


def _f(x: Any) -> float:
    return round(float(x), 4)


def smape(y: np.ndarray, p: np.ndarray) -> float:
    """Symmetric MAPE in percent; a day with zero actual and zero predicted counts as 0."""
    denom = np.abs(y) + np.abs(p)
    ratio = np.divide(2 * np.abs(y - p), denom, out=np.zeros_like(denom), where=denom > 0)
    return float(100 * ratio.mean())


def pinball(y: np.ndarray, q_pred: np.ndarray, q: float) -> float:
    diff = y - q_pred
    return float(np.mean(np.maximum(q * diff, (q - 1) * diff)))


def regression_metrics(
    y: Sequence[float] | np.ndarray, p50: np.ndarray, band: np.ndarray | None = None
) -> dict[str, float]:
    """MAE, RMSE, sMAPE and, when a (n, 3) p10/p50/p90 band is given, coverage, width, pinball."""
    yv = np.asarray(y, dtype=float)
    out = {
        "mae": _f(np.abs(yv - p50).mean()),
        "rmse": _f(np.sqrt(((yv - p50) ** 2).mean())),
        "smape": _f(smape(yv, p50)),
    }
    if band is not None:
        out["coverage_80"] = _f(((yv >= band[:, 0]) & (yv <= band[:, 2])).mean())
        out["mean_width_80"] = _f((band[:, 2] - band[:, 0]).mean())
        for i, q in enumerate(QUANTILES):
            out[f"pinball_p{int(q * 100)}"] = _f(pinball(yv, band[:, i], q))
    return out


def brier(y_true: np.ndarray, proba: np.ndarray, classes: Sequence[str]) -> float:
    """Multiclass Brier score: mean over days of the summed squared probability error."""
    onehot = (np.asarray(y_true)[:, None] == np.asarray(classes)[None, :]).astype(float)
    return float(((proba - onehot) ** 2).sum(axis=1).mean())


def classification_metrics(
    y_true: np.ndarray, proba: np.ndarray, classes: Sequence[str]
) -> dict[str, Any]:
    """Per-class precision/recall/F1, macro F1, High recall, OvR ROC-AUC, Brier, confusion.
    proba columns follow `classes`; they are reordered to CLASSES."""
    order = [list(classes).index(c) for c in CLASSES]
    proba = proba[:, order]
    pred = np.asarray(CLASSES, dtype=object)[proba.argmax(axis=1)]
    p, r, f, s = precision_recall_fscore_support(
        y_true, pred, labels=list(CLASSES), zero_division=0
    )
    present = [c for c in CLASSES if (y_true == c).any()]
    # roc_auc_score wants labels in sorted order, with proba columns to match.
    ordered = sorted(CLASSES)
    try:
        auc = roc_auc_score(
            y_true,
            proba[:, [CLASSES.index(c) for c in ordered]],
            multi_class="ovr",
            labels=ordered,
            average="macro",
        )
    except ValueError:
        auc = float("nan")
    return {
        "per_class": {
            c: {"precision": _f(p[i]), "recall": _f(r[i]), "f1": _f(f[i]), "support": int(s[i])}
            for i, c in enumerate(CLASSES)
        },
        "macro_f1": _f(f1_score(y_true, pred, labels=present, average="macro", zero_division=0)),
        "recall_high": _f(r[CLASSES.index("high")]),
        "roc_auc_ovr": _f(auc),
        "brier": _f(brier(y_true, proba, CLASSES)),
        "confusion": confusion_matrix(y_true, pred, labels=list(CLASSES)).tolist(),
        "labels": list(CLASSES),
    }


def report_markdown(run: dict[str, Any]) -> str:
    """Human-readable run report written to ops/reports/models/<run_id>.md."""
    m = run["metrics"]
    lines = [
        f"# Model run {run['run_id']}",
        "",
        f"- Feature set: **{run['feature_set']}** ({len(run['feature_list'])} features)",
        f"- Dataset: {', '.join(run['dataset_ids'])} ({run['rows']['train']} train rows, "
        f"{run['rows']['holdout']} holdout rows, split by {run['split']})",
        f"- Seed: {run['seed']}; tuned: {run['tuned']}",
        f"- Burden thresholds ({run['thresholds_source']}): "
        f"low <= {run['thresholds'][0]:.2f} h < moderate <= {run['thresholds'][1]:.2f} h < high",
        "",
        "## Regression (time-ordered holdout)",
        "",
        "| Model | MAE | RMSE | sMAPE | 80% coverage | 80% width |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for name, r in m["regression"].items():
        cov = r.get("coverage_80")
        width = r.get("mean_width_80")
        lines.append(
            f"| {name} | {r['mae']:.3f} | {r['rmse']:.3f} | {r['smape']:.1f} | "
            f"{'' if cov is None else f'{cov:.3f}'} | {'' if width is None else f'{width:.2f}'} |"
        )
    imp = m["improvement_vs_best_baseline"]
    lines += [
        "",
        f"Gradient boosting p50 MAE is {imp['ratio']:.3f} x the best baseline "
        f"({imp['best_baseline']}), a {100 * (1 - imp['ratio']):.1f}% improvement.",
        "",
        "## Burden classes",
        "",
        "| Model | Macro F1 | Recall High | ROC-AUC | Brier |",
        "| --- | --- | --- | --- | --- |",
    ]
    for name, c in m["classification"].items():
        lines.append(
            f"| {name} | {c['macro_f1']:.3f} | {c['recall_high']:.3f} | "
            f"{c['roc_auc_ovr']:.3f} | {c['brier']:.3f} |"
        )
    if "feature_sets" in m:
        lines += [
            "",
            "## Feature sets (p50 on the same holdout)",
            "",
            "| Feature set | MAE | 80% coverage |",
            "| --- | --- | --- |",
        ]
        for name, r in m["feature_sets"].items():
            lines.append(f"| {name} | {r['mae']:.3f} | {r['coverage_80']:.3f} |")
    if run.get("shap_global"):
        lines += [
            "",
            "## Global importance (mean |SHAP|, hours)",
            "",
            "| Feature | Mean abs SHAP |",
            "| --- | --- |",
            *(f"| {g['feature']} | {g['mean_abs_shap']:.3f} |" for g in run["shap_global"]),
            "",
            f"![SHAP beeswarm]({run['run_id']}_shap.png)",
            "",
            "Staffing directions (SHAP slope per unit, must be <= 0; mean SHAP in brackets): "
            + ", ".join(
                f"{k} {v['slope']:+.3f} ({v['mean_shap']:+.3f})"
                for k, v in run.get("shap_direction", {}).items()
            ),
        ]
    lines += ["", "## Hyperparameters", "", "```json", _json(run["params"]), "```", ""]
    return "\n".join(lines)


def _json(obj: Any) -> str:
    import json

    return json.dumps(obj, indent=2, sort_keys=True)
