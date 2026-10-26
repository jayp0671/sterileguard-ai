"""Baselines every model must beat (SG-13, plan §12.3)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.linear_model import LogisticRegression, RidgeCV
from sklearn.pipeline import Pipeline

from sg_ml.models import linear_preprocessor

RULE_FEATURE = "patients_per_morning_staff"


class RuleBaseline(RegressorMixin, BaseEstimator):  # type: ignore[misc]
    """The proposal's patients-per-technician rule: OT = a * max(0, ppm - b).

    b is chosen on a grid of training quantiles and a by least squares for each b; the pair
    with the lowest squared error wins."""

    def fit(self, X: pd.DataFrame, y: pd.Series) -> RuleBaseline:
        ppm = X[RULE_FEATURE].to_numpy(dtype=float)
        yv = np.asarray(y, dtype=float)
        best = (np.inf, 0.0, 0.0)
        for b in np.unique(np.quantile(ppm, np.linspace(0, 0.99, 100))):
            h = np.maximum(0.0, ppm - b)
            denom = float(h @ h)
            a = float(h @ yv) / denom if denom > 0 else 0.0
            sse = float(((a * h - yv) ** 2).sum())
            if sse < best[0]:
                best = (sse, a, float(b))
        self.a_, self.b_ = best[1], best[2]
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        ppm = X[RULE_FEATURE].to_numpy(dtype=float)
        return np.asarray(self.a_ * np.maximum(0.0, ppm - self.b_))


def ridge(names: Sequence[str]) -> Pipeline:
    return Pipeline(
        [
            ("pre", linear_preprocessor(names)),
            ("model", RidgeCV(alphas=np.logspace(-3, 3, 25))),
        ]
    )


def logistic(names: Sequence[str], *, balanced: bool, seed: int) -> Pipeline:
    weight: Any = "balanced" if balanced else None
    return Pipeline(
        [
            ("pre", linear_preprocessor(names)),
            ("model", LogisticRegression(max_iter=5000, class_weight=weight, random_state=seed)),
        ]
    )
