"""SHAP explanations of the central estimate (SG-14, plan §12.5).

TreeExplainer runs on the p50 model in transformed feature space; contributions of transformed
columns are summed back to the original feature (one-hot columns of a linear pipeline map to
their source feature; the tree pipeline's ordinal codes map one to one). The tree-path-dependent
algorithm is used because it is exactly additive for HistGradientBoosting: the interventional
algorithm with a background sample was off by about 0.6 hours in shap 0.54. The synthetic
background rows are still stored in the artifact for reference and later algorithms.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline

from sg_ml.features import REGISTRY, STAFFING

TOP_N = 5
OTHER = "other"
BACKGROUND_ROWS = 200


@dataclass(frozen=True)
class Driver:
    feature: str
    value: Any
    contribution_hours: float
    rank: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Explanation:
    expected_value: float
    prediction: float
    drivers: list[Driver]


def source_feature(column: str, features: Sequence[str]) -> str:
    """Original feature of a transformed column (exact name, or a one-hot '<feature>_<level>')."""
    if column in features:
        return column
    matches = [f for f in features if column.startswith(f"{f}_")]
    if not matches:
        raise KeyError(f"cannot map transformed column {column!r} to a feature")
    return max(matches, key=len)


def to_feature_space(
    values: np.ndarray, columns: Sequence[str], features: Sequence[str]
) -> pd.DataFrame:
    """Sum SHAP columns of the same source feature: (n, transformed) -> (n, features)."""
    frame = pd.DataFrame(values, columns=list(columns))
    groups = [source_feature(c, features) for c in columns]
    summed = frame.T.groupby(groups, sort=False).sum().T
    return summed.reindex(columns=list(features), fill_value=0.0)


class Explainer:
    """Wraps shap.TreeExplainer for a fitted tree Pipeline (pre -> model)."""

    def __init__(self, pipeline: Pipeline, features: Sequence[str]) -> None:
        import shap

        self.pipeline = pipeline
        self.features = list(features)
        self.pre, self.model = pipeline[0], pipeline[-1]
        self._tree = shap.TreeExplainer(self.model, feature_perturbation="tree_path_dependent")
        self.expected_value = float(np.ravel(self._tree.expected_value)[0])

    def shap_values(self, X: pd.DataFrame) -> pd.DataFrame:
        Xt = self.pre.transform(X[self.features])
        cols = list(self.pre.get_feature_names_out())
        raw = np.asarray(self._tree.shap_values(np.asarray(Xt, dtype=float)))
        return to_feature_space(raw, cols, self.features).set_axis(X.index)

    def raw_prediction(self, X: pd.DataFrame) -> np.ndarray:
        return np.asarray(self.pipeline.predict(X[self.features]), dtype=float)

    def explain(self, row: pd.DataFrame, top_n: int = TOP_N) -> Explanation:
        """Top drivers by absolute contribution plus one 'other' entry for the rest. The
        expected value plus every driver equals the model output for the row."""
        if len(row) != 1:
            raise ValueError("explain takes exactly one row")
        contrib = self.shap_values(row).iloc[0]
        order = contrib.abs().sort_values(ascending=False, kind="stable").index
        top, rest = list(order[:top_n]), list(order[top_n:])
        drivers = [
            Driver(f, _plain(row.iloc[0][f]), float(contrib[f]), rank)
            for rank, f in enumerate(top, start=1)
        ]
        if rest:
            drivers.append(Driver(OTHER, None, float(contrib[rest].sum()), len(top) + 1))
        return Explanation(self.expected_value, float(self.raw_prediction(row)[0]), drivers)

    def global_importance(self, X: pd.DataFrame, top: int = 10) -> list[dict[str, Any]]:
        """Mean |SHAP| per feature over X (the holdout), largest first."""
        mean_abs = self.shap_values(X).abs().mean().sort_values(ascending=False)
        return [
            {"feature": str(f), "mean_abs_shap": round(float(v), 4)}
            for f, v in mean_abs[:top].items()
        ]

    def direction_check(self, X: pd.DataFrame) -> dict[str, dict[str, float]]:
        """Per staffing feature: the mean SHAP value (the ticket's measure) and the slope of SHAP
        against the feature's value. SHAP values average to about zero over the data by
        construction, so the mean is noise around 0; the slope says whether more staff pushes
        predicted overtime down, which is what plan §12.4 asks. SG-17 gates on slope <= 0
        (ADR-0006)."""
        sv = self.shap_values(X)
        out: dict[str, dict[str, float]] = {}
        for f in STAFFING:
            if f not in sv.columns:
                continue
            x = X[f].astype(float).to_numpy()
            s = sv[f].to_numpy()
            var = float(np.var(x))
            slope = float(np.cov(x, s, bias=True)[0, 1] / var) if var > 0 else 0.0
            out[f] = {"mean_shap": round(float(s.mean()), 6), "slope": round(slope, 6)}
        return out


def background_sample(X: pd.DataFrame, seed: int, n: int = BACKGROUND_ROWS) -> pd.DataFrame:
    """At most n training rows (simulated, synthetic) kept in the artifact."""
    return X.sample(min(n, len(X)), random_state=seed).reset_index(drop=True)


def beeswarm(explainer: Explainer, X: pd.DataFrame, path: Any, max_display: int = 12) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import shap

    sv = explainer.shap_values(X)
    data = X[explainer.features].apply(
        lambda c: c if REGISTRY[c.name].kind != "categorical" else c.astype("category").cat.codes
    )
    exp = shap.Explanation(
        values=sv.to_numpy(),
        base_values=np.full(len(sv), explainer.expected_value),
        data=data.to_numpy(dtype=float),
        feature_names=explainer.features,
    )
    shap.plots.beeswarm(exp, max_display=max_display, show=False)
    plt.gcf().set_size_inches(9, 6)
    plt.tight_layout()
    plt.savefig(path, dpi=200)
    plt.close("all")


def _plain(value: Any) -> Any:
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and np.isnan(value):
        return None
    return value
