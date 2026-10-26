"""Models, baselines and metrics (SG-13)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from hypothesis import given
from hypothesis import strategies as st
from hypothesis.extra.numpy import arrays

from sg_ml import evaluate
from sg_ml.baselines import RuleBaseline
from sg_ml.features import FEATURE_SETS, STAFFING, TARGET, add_features, build_matrix
from sg_ml.models import (
    CLASSES,
    TIE_JITTER,
    QuantileModel,
    burden_class,
    burden_thresholds,
    combine_quantiles,
)

from .conftest import FAST_PARAMS

floats = arrays(np.float64, 20, elements=st.floats(-5, 50, allow_nan=False))


@given(floats, floats, floats)
def test_combined_band_never_crosses_or_goes_negative(
    a: np.ndarray, b: np.ndarray, c: np.ndarray
) -> None:
    band = combine_quantiles([a, b, c])
    assert (band >= 0).all()
    assert (band[:, 0] <= band[:, 1]).all() and (band[:, 1] <= band[:, 2]).all()


def test_combine_quantiles_removes_jitter() -> None:
    band = combine_quantiles([np.array([TIE_JITTER / 2]), np.array([3.0]), np.array([5.0])])
    assert band.tolist() == [[0.0, 3.0, 5.0 - TIE_JITTER]]
    # Bounds are widened to contain the central estimate, never the other way round.
    crossed = combine_quantiles([np.array([4.0]), np.array([3.0]), np.array([2.0])])
    assert crossed.tolist() == [[3.0, 3.0, 3.0]]


def test_burden_class_boundaries() -> None:
    t = burden_thresholds(pd.Series(np.arange(9.0)))
    assert t == pytest.approx([8 / 3, 16 / 3])
    labels = burden_class(np.array([0.0, t[0], t[0] + 0.01, t[1], 8.0]), t)
    assert labels.tolist() == ["low", "low", "moderate", "moderate", "high"]
    assert set(CLASSES) == {"low", "moderate", "high"}


def test_rule_baseline_recovers_a_and_b() -> None:
    ppm = np.linspace(40, 160, 400)
    y = 0.25 * np.maximum(0, ppm - 100)
    rule = RuleBaseline().fit(pd.DataFrame({"patients_per_morning_staff": ppm}), pd.Series(y))
    assert rule.a_ == pytest.approx(0.25, rel=0.05)
    assert rule.b_ == pytest.approx(100, abs=2)


def test_quantile_model_is_monotone_in_staffing(rows: pd.DataFrame, ctx: object) -> None:
    F = add_features(rows, ctx).reset_index(drop=True)  # type: ignore[arg-type]
    names = list(FEATURE_SETS["full"])
    X, y = build_matrix(F, names), F[TARGET].astype(float)
    model = QuantileModel().fit(X, y, names, FAST_PARAMS, seed=1)
    sample = X.sample(60, random_state=0)
    base = model.predict(sample)
    for feat in STAFFING:
        bumped = sample.copy()
        bumped[feat] = bumped[feat] + 1
        assert (model.predict(bumped)[:, 1] <= base[:, 1] + 1e-9).all(), feat


def test_regression_metrics_by_hand() -> None:
    y = np.array([0.0, 2.0, 4.0])
    p = np.array([0.0, 1.0, 6.0])
    band = np.array([[0.0, 0.0, 1.0], [0.5, 1.0, 3.0], [5.0, 6.0, 7.0]])
    m = evaluate.regression_metrics(y, p, band)
    assert m["mae"] == pytest.approx(1.0)
    assert m["rmse"] == pytest.approx(np.sqrt(5 / 3), abs=1e-4)
    # sMAPE: 0 (both zero), 2*1/3, 2*2/10 -> mean * 100
    assert m["smape"] == pytest.approx(100 * (0 + 2 / 3 + 0.4) / 3, abs=1e-3)
    assert m["coverage_80"] == pytest.approx(2 / 3, abs=1e-4)
    assert m["mean_width_80"] == pytest.approx(11 / 6, abs=1e-4)
    assert m["pinball_p50"] == pytest.approx(0.5, abs=1e-4)


def test_classification_metrics_perfect_and_brier() -> None:
    y = np.array(["low", "moderate", "high", "high"], dtype=object)
    proba = np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1], [0, 0, 1]], dtype=float)
    m = evaluate.classification_metrics(y, proba, list(CLASSES))
    assert m["macro_f1"] == 1.0 and m["recall_high"] == 1.0
    assert m["brier"] == 0.0 and m["roc_auc_ovr"] == 1.0
    assert m["confusion"] == [[1, 0, 0], [0, 1, 0], [0, 0, 2]]
    # Columns given in another order are realigned to CLASSES.
    shuffled = evaluate.classification_metrics(y, proba[:, [2, 0, 1]], ["high", "low", "moderate"])
    assert shuffled["macro_f1"] == 1.0
    uniform = evaluate.brier(y, np.full((4, 3), 1 / 3), list(CLASSES))
    assert uniform == pytest.approx(2 / 3)
