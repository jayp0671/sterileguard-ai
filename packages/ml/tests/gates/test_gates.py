"""Activation gates (SG-17): a sound model passes, and a leaky or flipped model fails."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from sg_ml import __main__ as cli
from sg_ml import gates
from sg_ml.features import FEATURE_SETS, FeatureContext
from sg_ml.testing import FAST_PARAMS, synthetic_rows
from sg_ml.train import TrainResult, save_run, train


@pytest.fixture(scope="module")
def good(rows: pd.DataFrame, ctx: FeatureContext) -> TrainResult:
    return train(rows, {"id": "synthetic"}, ctx, "full", seed=5, params=FAST_PARAMS)


def by_name(results: list[gates.GateResult]) -> dict[str, gates.GateResult]:
    return {r.name: r for r in results}


def test_sound_model_passes_structural_gates(good: TrainResult, rows: pd.DataFrame) -> None:
    results = by_name(gates.run_gates(good.run, good.artifact, rows))
    for name in ("no_leakage", "monotonicity", "shap_direction", "determinism"):
        assert results[name].passed, results[name].message
    assert results["real_data_check"].required is False
    assert results["real_data_check"].passed is False


def test_leaky_feature_fails_no_leakage() -> None:
    leaky = [*FEATURE_SETS["full"], "end_backlog_units"]
    assert not gates.no_leakage(leaky).passed
    assert not gates.no_leakage([*FEATURE_SETS["core"], "ot_labor_hours"]).passed
    assert gates.no_leakage(FEATURE_SETS["full"]).passed


def test_flipped_staffing_fails_monotonicity_or_shap(ctx: FeatureContext) -> None:
    """A model trained without its constraints on data where staffing raises overtime."""
    flipped = synthetic_rows(n_seq=20, seed=9, invert_staffing=True)
    bad = train(flipped, {"id": "flipped"}, ctx, "full", seed=5, params=FAST_PARAMS, monotone=False)
    results = by_name(gates.run_gates(bad.run, bad.artifact, flipped))
    assert not (results["monotonicity"].passed and results["shap_direction"].passed)
    assert not gates.passed(list(results.values()))


def test_metric_gates_thresholds() -> None:
    def run(model_mae: float, cov: float, brier: float) -> dict[str, Any]:
        return {
            "metrics": {
                "regression": {
                    "hgb_p50": {"mae": model_mae, "coverage_80": cov},
                    "baseline_ridge": {"mae": 2.0},
                    "baseline_rule": {"mae": 5.0},
                },
                "classification": {
                    "hgb_classifier": {"brier": brier},
                    "baseline_logistic": {"brier": 0.3},
                },
            }
        }

    assert gates.beats_baselines(run(1.7, 0.8, 0.2)).passed  # 0.85 x 2.0 = 1.7
    assert not gates.beats_baselines(run(1.71, 0.8, 0.2)).passed
    assert gates.interval_coverage(run(1, 0.75, 0.2)).passed
    assert not gates.interval_coverage(run(1, 0.86, 0.2)).passed
    assert not gates.classifier_calibration(run(1, 0.8, 0.31)).passed
    real = gates.real_data_check(0.9, 12)
    assert real.passed and not real.required


def test_evaluate_writes_gates_and_exits_nonzero_on_failure(
    good: TrainResult, rows: pd.DataFrame, tmp_path: Path
) -> None:
    sim = tmp_path / "sim"
    sim.mkdir()
    rows.to_parquet(sim / "synthetic.parquet", index=False)
    run_dir = save_run(good, tmp_path / "runs", tmp_path / "reports")
    args = [
        "evaluate",
        "--run",
        good.run["run_id"],
        "--runs-dir",
        str(tmp_path / "runs"),
        "--sim-dir",
        str(sim),
        "--reports-dir",
        str(tmp_path / "reports"),
        "--json",
    ]
    code = cli.main(args)
    saved = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
    assert {g["name"] for g in saved["gates"]} >= {"beats_baselines", "monotonicity"}
    assert code == (0 if saved["gates_passed"] else 1)
    report = (tmp_path / "reports" / f"{good.run['run_id']}.md").read_text(encoding="utf-8")
    assert "## Activation gates" in report
