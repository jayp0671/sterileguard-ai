"""Model builders (SG-13, plan §12.3). Every model is a scikit-learn Pipeline whose first step
is the ColumnTransformer, so training and serving share identical preprocessing and the whole
pipeline is saved inside the artifact."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import (
    HistGradientBoostingClassifier,
    HistGradientBoostingRegressor,
    RandomForestRegressor,
)
from sklearn.impute import SimpleImputer
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler

from sg_ml.features import categorical, monotone_constraints

QUANTILES = (0.1, 0.5, 0.9)
CLASSES = ("low", "moderate", "high")

# Untuned defaults; sg ml train --tune replaces them with the Optuna best.
DEFAULT_PARAMS: dict[str, Any] = {
    "learning_rate": 0.05,
    "max_iter": 400,
    "max_leaf_nodes": 31,
    "min_samples_leaf": 20,
    "l2_regularization": 0.0,
}


def tree_preprocessor(names: Sequence[str]) -> ColumnTransformer:
    """Numeric passthrough (trees handle NaN) and ordinal-encoded categoricals.

    The trees treat the ordinal codes as numbers, not as native categorical splits: SHAP's
    TreeExplainer (0.54) mis-reads HistGradientBoosting categorical splits (SG-14)."""
    cats = categorical(names)
    nums = [n for n in names if n not in cats]
    ct = ColumnTransformer(
        [
            ("num", "passthrough", nums),
            (
                "cat",
                OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=np.nan),
                cats,
            ),
        ],
        verbose_feature_names_out=False,
    )
    return ct.set_output(transform="pandas")


def linear_preprocessor(names: Sequence[str]) -> ColumnTransformer:
    """Imputed and scaled numerics, one-hot categoricals (unknown levels ignored)."""
    cats = categorical(names)
    nums = [n for n in names if n not in cats]
    return ColumnTransformer(
        [
            ("num", make_pipeline(SimpleImputer(strategy="median"), StandardScaler()), nums),
            ("cat", OneHotEncoder(handle_unknown="ignore"), cats),
        ],
        verbose_feature_names_out=False,
    )


def _tree_order(names: Sequence[str]) -> list[str]:
    cats = categorical(names)
    return [n for n in names if n not in cats] + cats


def hgb_regressor(
    names: Sequence[str],
    params: dict[str, Any],
    seed: int,
    *,
    quantile: float | None = None,
    monotone: bool = True,
) -> Pipeline:
    """Monotone-constrained gradient boosting; squared error, or quantile loss when given.
    monotone=False exists only so the SG-17 gate tests can train a model that breaks them."""
    order = _tree_order(names)
    kw: dict[str, Any] = {"loss": "quantile", "quantile": quantile} if quantile else {}
    model = HistGradientBoostingRegressor(
        **(kw or {"loss": "squared_error"}),
        **params,
        monotonic_cst=monotone_constraints(order) if monotone else None,
        categorical_features=None,
        early_stopping=True,
        random_state=seed,
    )
    return Pipeline([("pre", tree_preprocessor(names)), ("model", model)])


def hgb_classifier(names: Sequence[str], params: dict[str, Any], seed: int) -> Any:
    base = Pipeline(
        [
            ("pre", tree_preprocessor(names)),
            (
                "model",
                HistGradientBoostingClassifier(
                    **params,
                    categorical_features=None,
                    early_stopping=True,
                    random_state=seed,
                ),
            ),
        ]
    )
    return CalibratedClassifierCV(base, method="isotonic", cv=TimeSeriesSplit(n_splits=3))


def random_forest(names: Sequence[str], seed: int) -> Pipeline:
    pre = ColumnTransformer(
        [
            (
                "num",
                SimpleImputer(strategy="median"),
                [n for n in names if n not in categorical(names)],
            ),
            (
                "cat",
                OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1),
                categorical(names),
            ),
        ],
        verbose_feature_names_out=False,
    )
    # Single-threaded so retraining with the same seed reproduces predictions bit for bit.
    rf = RandomForestRegressor(n_estimators=300, min_samples_leaf=5, n_jobs=1, random_state=seed)
    return Pipeline([("pre", pre), ("model", rf)])


# ---------------------------------------------------------------------------
# Ranges and classes
# ---------------------------------------------------------------------------


@dataclass
class QuantileModel:
    """The 80% range and the central estimate.

    p10 and p90 are quantile-loss models. The central estimate ("most likely", stored as p50) is
    the squared-error model: scikit-learn re-fits quantile-loss leaf values after each tree, which
    breaks the monotonic constraints (adding a staff member raised the quantile median by up to
    2.5 hours), while the squared-error model keeps them exactly. ADR-0005."""

    pipelines: dict[float, Pipeline] = field(default_factory=dict)

    def fit(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        names: Sequence[str],
        params: dict[str, Any],
        seed: int,
        *,
        monotone: bool = True,
    ) -> QuantileModel:
        yj = jitter_target(y, seed)
        for q in QUANTILES:
            if q == 0.5:
                self.pipelines[q] = hgb_regressor(names, params, seed, monotone=monotone).fit(X, y)
            else:
                self.pipelines[q] = hgb_regressor(
                    names, params, seed, quantile=q, monotone=monotone
                ).fit(X, yj)
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Array of shape (n, 3): p10, p50, p90."""
        return combine_quantiles([self.pipelines[q].predict(X) for q in QUANTILES])


# HistGradientBoosting's quantile loss (scikit-learn 1.9) never leaves its starting value when
# that value ties with many targets: a quarter of days have exactly 0 overtime, so the p10 model
# predicted 0 for every day. A seeded jitter of at most TIE_JITTER hours on the training target
# of the p10 and p90 models breaks the ties; combine_quantiles subtracts it again. ADR-0005.
TIE_JITTER = 0.01


def jitter_target(y: pd.Series, seed: int) -> pd.Series:
    rng = np.random.default_rng(seed)
    return y.astype(float) + rng.uniform(0, TIE_JITTER, len(y))


def combine_quantiles(raw: Sequence[np.ndarray]) -> np.ndarray:
    """Raw p10/p50/p90 predictions -> (n, 3) band, clipped at 0. The central estimate is kept
    as predicted (so it stays monotone); the bounds lose the jitter and are widened to contain
    it, so the three never cross. The API uses this too, so serving matches evaluation."""
    lo, mid, hi = (np.asarray(r, dtype=float) for r in raw)
    mid = np.clip(mid, 0, None)
    lo = np.clip(np.minimum(lo - TIE_JITTER, mid), 0, None)
    hi = np.maximum(hi - TIE_JITTER, mid)
    return np.column_stack([lo, mid, hi])


def burden_thresholds(y: pd.Series) -> list[float]:
    """Provisional Low/Moderate/High cut points: terciles of simulated overtime."""
    return [float(v) for v in np.quantile(y.astype(float), [1 / 3, 2 / 3])]


def burden_class(y: np.ndarray | pd.Series, thresholds: Sequence[float]) -> np.ndarray:
    """low if y <= t1, moderate if y <= t2, otherwise high."""
    idx = np.searchsorted(np.asarray(thresholds), np.asarray(y, dtype=float), side="left")
    return np.asarray(CLASSES, dtype=object)[idx]
