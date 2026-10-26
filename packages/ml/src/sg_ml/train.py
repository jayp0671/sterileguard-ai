"""Training run (SG-13): features, time-ordered split, baselines, gradient boosting with 80%
ranges, burden classifier, optional Optuna tuning, evaluation, and the run folder."""

from __future__ import annotations

import datetime as dt
import json
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import TimeSeriesSplit

from sg_ml import baselines, evaluate
from sg_ml.data import REPORTS_DIR, RUNS_DIR
from sg_ml.explain import Explainer, background_sample, beeswarm
from sg_ml.features import (
    FEATURE_SETS,
    TARGET,
    FeatureContext,
    add_features,
    build_matrix,
    resolve_feature_set,
    sequence_ids,
)
from sg_ml.models import (
    DEFAULT_PARAMS,
    TIE_JITTER,
    QuantileModel,
    burden_class,
    burden_thresholds,
    hgb_classifier,
    hgb_regressor,
    jitter_target,
    random_forest,
)

HOLDOUT_SHARE = 0.2
CV_SPLITS = 5


@dataclass
class TrainResult:
    run: dict[str, Any]
    artifact: dict[str, Any]
    holdout: pd.DataFrame
    # Holdout inputs for the SHAP beeswarm written by save_run.
    holdout_X: pd.DataFrame | None = None


def time_split(F: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, str]:
    """Simulated rows: first 80% of sequences train, last 20% holdout (never inside a sequence,
    carryover links its days). Real rows: strictly by date. Never shuffled."""
    if (F["source"] == "simulated").all():
        seq = sequence_ids(F).to_numpy()
        order = np.unique(seq)
        cut = order[int(np.floor(len(order) * (1 - HOLDOUT_SHARE)))]
        return seq < cut, seq >= cut, "sequence"
    dates = pd.to_datetime(F["date"])
    cut_date = dates.sort_values().iloc[int(np.floor(len(dates) * (1 - HOLDOUT_SHARE)))]
    return (dates < cut_date).to_numpy(), (dates >= cut_date).to_numpy(), "date"


def cv_folds(F: pd.DataFrame, n_splits: int = CV_SPLITS) -> list[tuple[np.ndarray, np.ndarray]]:
    """TimeSeriesSplit over sequence order (dates for real rows), as row positions."""
    seq = sequence_ids(F).to_numpy()
    key = (
        seq
        if (F["source"] == "simulated").all()
        else pd.to_datetime(F["date"]).to_numpy().astype("datetime64[D]").astype(int)
    )
    groups = np.unique(key)
    folds = []
    for tr, va in TimeSeriesSplit(n_splits=n_splits).split(groups):
        folds.append(
            (np.flatnonzero(np.isin(key, groups[tr])), np.flatnonzero(np.isin(key, groups[va])))
        )
    return folds


def tune(
    X: pd.DataFrame,
    y: pd.Series,
    F: pd.DataFrame,
    names: Sequence[str],
    seed: int,
    trials: int = 100,
) -> tuple[dict[str, Any], float]:
    """Optuna TPE over the gradient boosting parameters; objective: mean CV MAE of the central
    (squared-error) estimate that is served as p50."""
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    folds = cv_folds(F)

    def objective(trial: optuna.Trial) -> float:
        params = {
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "max_iter": trial.suggest_int("max_iter", 100, 1000, step=50),
            "max_leaf_nodes": trial.suggest_int("max_leaf_nodes", 8, 128, log=True),
            "min_samples_leaf": trial.suggest_int("min_samples_leaf", 5, 100, log=True),
            "l2_regularization": trial.suggest_float("l2_regularization", 1e-6, 10.0, log=True),
        }
        maes = []
        for tr, va in folds:
            m = hgb_regressor(names, params, seed).fit(X.iloc[tr], y.iloc[tr])
            pred = np.clip(m.predict(X.iloc[va]), 0, None)
            maes.append(float(np.abs(pred - y.iloc[va].to_numpy()).mean()))
        return float(np.mean(maes))

    study = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler(seed=seed))
    study.optimize(objective, n_trials=trials, n_jobs=1)
    return dict(study.best_params), float(study.best_value)


def _fit_band(
    F: pd.DataFrame,
    tr: np.ndarray,
    ho: np.ndarray,
    names: Sequence[str],
    params: dict[str, Any],
    seed: int,
) -> tuple[QuantileModel, np.ndarray]:
    X, y = build_matrix(F, names), F[TARGET].astype(float)
    model = QuantileModel().fit(X[tr], y[tr], names, params, seed)
    return model, model.predict(X[ho])


def train(
    df: pd.DataFrame,
    meta: dict[str, Any],
    ctx: FeatureContext,
    feature_set: str = "full",
    seed: int = 42,
    *,
    tune_trials: int = 0,
    params: dict[str, Any] | None = None,
) -> TrainResult:
    F = add_features(df, ctx).reset_index(drop=True)
    F = F[F[TARGET].notna()].reset_index(drop=True)
    names = resolve_feature_set(feature_set)
    tr, ho, how = time_split(F)
    X, y = build_matrix(F, names), F[TARGET].astype(float)
    y_ho = y[ho].to_numpy()

    cv_mae = None
    if params is None:
        params = dict(DEFAULT_PARAMS)
        if tune_trials:
            params, cv_mae = tune(
                X[tr], y[tr], F[tr].reset_index(drop=True), names, seed, tune_trials
            )

    # Main models
    quantiles, band = _fit_band(F, tr, ho, names, params, seed)
    # The quantile median, reported for comparison only (not monotone, ADR-0005).
    q50 = hgb_regressor(names, params, seed, quantile=0.5).fit(X[tr], jitter_target(y[tr], seed))
    rf = random_forest(names, seed).fit(X[tr], y[tr])

    # Baselines
    rule = baselines.RuleBaseline().fit(F.loc[tr, ["patients_per_morning_staff"]], y[tr])
    full_names = list(FEATURE_SETS["full"])
    X_full = build_matrix(F, full_names)
    ridge = baselines.ridge(full_names).fit(X_full[tr], y[tr])

    preds = {
        "hgb_p50": band[:, 1],
        "hgb_q50": np.clip(q50.predict(X[ho]) - TIE_JITTER, 0, None),
        "random_forest": np.clip(rf.predict(X[ho]), 0, None),
        "baseline_rule": rule.predict(F.loc[ho, ["patients_per_morning_staff"]]),
        "baseline_ridge": np.clip(ridge.predict(X_full[ho]), 0, None),
    }
    regression = {
        name: evaluate.regression_metrics(y_ho, p, band if name == "hgb_p50" else None)
        for name, p in preds.items()
    }
    base_names = [n for n in regression if n.startswith("baseline_")]
    best_base = min(base_names, key=lambda n: regression[n]["mae"])
    ratio = regression["hgb_p50"]["mae"] / regression[best_base]["mae"]

    # Burden classes (provisional: terciles of the simulated training overtime)
    thresholds = burden_thresholds(y[tr])
    c_tr, c_ho = burden_class(y[tr], thresholds), burden_class(y_ho, thresholds)
    clf = hgb_classifier(names, params, seed).fit(X[tr], c_tr)
    log_plain = baselines.logistic(full_names, balanced=False, seed=seed).fit(X_full[tr], c_tr)
    log_bal = baselines.logistic(full_names, balanced=True, seed=seed).fit(X_full[tr], c_tr)
    probas = {
        "hgb_classifier": (clf.predict_proba(X[ho]), list(clf.classes_)),
        "baseline_logistic": (log_plain.predict_proba(X_full[ho]), list(log_plain.classes_)),
        "baseline_logistic_balanced": (log_bal.predict_proba(X_full[ho]), list(log_bal.classes_)),
    }
    classification = {
        name: evaluate.classification_metrics(c_ho, p, cls) for name, (p, cls) in probas.items()
    }

    # SHAP on the served central estimate (SG-14): global importance, staffing directions.
    explainer = Explainer(quantiles.pipelines[0.5], names)
    shap_sample = X[ho].iloc[:: max(1, int(ho.sum()) // 500)]
    shap_global = explainer.global_importance(shap_sample)
    shap_direction = explainer.direction_check(shap_sample)

    # Both feature sets are always trained and reported on the same holdout.
    feature_sets: dict[str, dict[str, float]] = {}
    for other in FEATURE_SETS:
        other_band = (
            band
            if other == feature_set
            else _fit_band(F, tr, ho, list(FEATURE_SETS[other]), params, seed)[1]
        )
        feature_sets[other] = evaluate.regression_metrics(y_ho, other_band[:, 1], other_band)

    run_id = f"{dt.datetime.now(dt.UTC):%Y%m%d-%H%M%S}-{feature_set}-s{seed}"
    run: dict[str, Any] = {
        "run_id": run_id,
        "created_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "feature_set": feature_set,
        "feature_list": names,
        "dataset_ids": [str(meta["id"])],
        "sim_config_hash": ctx.sim_config_hash,
        "seed": seed,
        "tuned": bool(tune_trials),
        "tune_trials": tune_trials,
        "cv_mae": cv_mae,
        "params": params,
        "split": how,
        "rows": {"train": int(tr.sum()), "holdout": int(ho.sum())},
        "thresholds": thresholds,
        "thresholds_source": "simulated_provisional",
        "metrics": {
            "regression": regression,
            "classification": classification,
            "improvement_vs_best_baseline": {"best_baseline": best_base, "ratio": round(ratio, 4)},
            "feature_sets": feature_sets,
        },
        "rule_baseline": {"a": rule.a_, "b": rule.b_},
        "shap_global": shap_global,
        "shap_direction": shap_direction,
    }
    artifact: dict[str, Any] = {
        "pipeline_p10": quantiles.pipelines[0.1],
        "pipeline_p50": quantiles.pipelines[0.5],
        "pipeline_p90": quantiles.pipelines[0.9],
        "classifier": clf,
        "feature_list": names,
        "feature_set": feature_set,
        "thresholds": thresholds,
        "thresholds_source": "simulated_provisional",
        "context": ctx.to_dict(),
        "sim_config_hash": ctx.sim_config_hash,
        "params": params,
        "seed": seed,
        "dataset_ids": run["dataset_ids"],
        "explainer_background": background_sample(X[tr], seed),
    }
    holdout = pd.DataFrame(
        {
            "date": pd.to_datetime(F.loc[ho, "date"]).to_numpy(),
            "sequence": sequence_ids(F[ho]).to_numpy(),
            "actual": y_ho,
            "p10": band[:, 0],
            "p50": band[:, 1],
            "p90": band[:, 2],
            **{k: v for k, v in preds.items() if k != "hgb_p50"},
            "class_actual": c_ho,
            **{
                f"proba_{c}": probas["hgb_classifier"][0][:, i]
                for i, c in enumerate(probas["hgb_classifier"][1])
            },
        }
    )
    return TrainResult(run, artifact, holdout, holdout_X=shap_sample)


def save_run(
    result: TrainResult, runs_dir: Path = RUNS_DIR, reports_dir: Path = REPORTS_DIR
) -> Path:
    out: Path = runs_dir / str(result.run["run_id"])
    out.mkdir(parents=True, exist_ok=True)
    joblib.dump(result.artifact, out / "artifact.joblib", compress=3)
    (out / "metrics.json").write_text(json.dumps(result.run, indent=2), encoding="utf-8")
    result.holdout.to_parquet(out / "holdout.parquet", index=False)
    reports_dir.mkdir(parents=True, exist_ok=True)
    if result.holdout_X is not None:
        explainer = Explainer(result.artifact["pipeline_p50"], result.artifact["feature_list"])
        beeswarm(explainer, result.holdout_X, out / "shap_beeswarm.png")
        shutil.copyfile(out / "shap_beeswarm.png", reports_dir / f"{result.run['run_id']}_shap.png")
    (reports_dir / f"{result.run['run_id']}.md").write_text(
        evaluate.report_markdown(result.run), encoding="utf-8"
    )
    return out


def load_runs(runs_dir: Path = RUNS_DIR) -> list[dict[str, Any]]:
    runs = []
    for path in sorted(runs_dir.glob("*/metrics.json")):
        runs.append(json.loads(path.read_text(encoding="utf-8")))
    return runs
