"""Training run: time-ordered split, determinism, run folder (SG-13)."""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

from sg_ml import __main__ as cli
from sg_ml.features import FeatureContext, add_features, sequence_ids
from sg_ml.train import TrainResult, cv_folds, load_runs, save_run, time_split, train

from .conftest import FAST_PARAMS, synthetic_rows


@pytest.fixture(scope="module")
def result(rows: pd.DataFrame, ctx: FeatureContext) -> TrainResult:
    return train(rows, {"id": "synthetic"}, ctx, "full", seed=3, params=FAST_PARAMS)


def test_split_is_by_whole_sequence_and_time_ordered(
    rows: pd.DataFrame, ctx: FeatureContext
) -> None:
    F = add_features(rows, ctx).reset_index(drop=True)
    tr, ho, how = time_split(F)
    seq = sequence_ids(F)
    assert how == "sequence"
    assert not set(seq[tr]) & set(seq[ho])
    assert F.loc[tr, "date"].max() < F.loc[ho, "date"].min()
    assert ho.mean() == pytest.approx(0.2)


def test_real_rows_split_by_date(rows: pd.DataFrame, ctx: FeatureContext) -> None:
    F = add_features(rows.head(50).assign(source="real"), ctx).reset_index(drop=True)
    tr, ho, how = time_split(F)
    assert how == "date"
    assert F.loc[tr, "date"].max() < F.loc[ho, "date"].min()


def test_cv_folds_follow_sequence_order(rows: pd.DataFrame, ctx: FeatureContext) -> None:
    F = add_features(rows, ctx).reset_index(drop=True)
    seq = sequence_ids(F).to_numpy()
    for tr, va in cv_folds(F):
        assert seq[tr].max() < seq[va].min()


def test_run_contents(result: TrainResult) -> None:
    run = result.run
    reg = run["metrics"]["regression"]
    assert {"hgb_p50", "hgb_q50", "random_forest", "baseline_rule", "baseline_ridge"} <= set(reg)
    assert set(run["metrics"]["feature_sets"]) == {"full", "core"}
    assert {"hgb_classifier", "baseline_logistic", "baseline_logistic_balanced"} == set(
        run["metrics"]["classification"]
    )
    assert run["thresholds_source"] == "simulated_provisional"
    assert reg["hgb_p50"]["mae"] < reg["baseline_rule"]["mae"]
    art = result.artifact
    for key in ("pipeline_p10", "pipeline_p50", "pipeline_p90", "classifier", "feature_list"):
        assert key in art
    band = result.holdout[["p10", "p50", "p90"]].to_numpy()
    assert (np.diff(band, axis=1) >= 0).all() and (band >= 0).all()


def test_same_seed_reproduces_metrics_exactly(
    rows: pd.DataFrame, ctx: FeatureContext, result: TrainResult
) -> None:
    again = train(rows, {"id": "synthetic"}, ctx, "full", seed=3, params=FAST_PARAMS)
    assert again.run["metrics"] == result.run["metrics"]
    pd.testing.assert_frame_equal(again.holdout, result.holdout)


def test_tuning_is_seeded(ctx: FeatureContext) -> None:
    small = synthetic_rows(n_seq=12, seed=11)
    a = train(small, {"id": "s"}, ctx, "core", seed=5, tune_trials=3)
    b = train(small, {"id": "s"}, ctx, "core", seed=5, tune_trials=3)
    assert a.run["params"] == b.run["params"]
    assert a.run["tuned"] and a.run["cv_mae"] is not None


def test_save_run_and_compare(
    result: TrainResult, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = save_run(result, tmp_path / "runs", tmp_path / "reports")
    assert (out / "artifact.joblib").exists() and (out / "holdout.parquet").exists()
    metrics = json.loads((out / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["run_id"] == result.run["run_id"]
    report = (tmp_path / "reports" / f"{result.run['run_id']}.md").read_text(encoding="utf-8")
    assert "Gradient boosting p50 MAE" in report
    art = joblib.load(out / "artifact.joblib")
    assert art["feature_set"] == "full"
    assert [r["run_id"] for r in load_runs(tmp_path / "runs")] == [result.run["run_id"]]
    assert cli.main(["compare", "--runs-dir", str(tmp_path / "runs"), "--json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert rows[0]["feature_set"] == "full"
