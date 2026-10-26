"""SHAP drivers, driver sentences and the model registry (SG-14)."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from sg_ml import driver_text as dtx
from sg_ml.explain import OTHER, Explainer, source_feature, to_feature_space
from sg_ml.features import FEATURE_SETS, REGISTRY, STAFFING, FeatureContext, build_matrix
from sg_ml.registry import build_card, make_version, register
from sg_ml.train import TrainResult, save_run, train

from .conftest import FAST_PARAMS, synthetic_rows

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def result(rows: pd.DataFrame, ctx: FeatureContext) -> TrainResult:
    return train(rows, {"id": "synthetic"}, ctx, "full", seed=4, params=FAST_PARAMS)


@pytest.fixture(scope="module")
def explainer(result: TrainResult) -> Explainer:
    return Explainer(result.artifact["pipeline_p50"], result.artifact["feature_list"])


@pytest.fixture(scope="module")
def X(rows: pd.DataFrame, ctx: FeatureContext) -> pd.DataFrame:
    from sg_ml.features import add_features

    return build_matrix(add_features(rows, ctx), "full")


def test_drivers_plus_expected_value_equal_p50(explainer: Explainer, X: pd.DataFrame) -> None:
    for i in range(0, len(X), 97):
        ex = explainer.explain(X.iloc[[i]])
        assert len(ex.drivers) == 6 and ex.drivers[-1].feature == OTHER
        assert [d.rank for d in ex.drivers] == [1, 2, 3, 4, 5, 6]
        total = ex.expected_value + sum(d.contribution_hours for d in ex.drivers)
        assert total == pytest.approx(ex.prediction, abs=0.01)
        top = [abs(d.contribution_hours) for d in ex.drivers[:5]]
        assert top == sorted(top, reverse=True)


def test_one_hot_columns_map_back_to_their_feature() -> None:
    feats = ["day_of_week", "regular_patients", "is_monday"]
    assert source_feature("day_of_week_mon", feats) == "day_of_week"
    assert source_feature("regular_patients", feats) == "regular_patients"
    with pytest.raises(KeyError):
        source_feature("unknown_col", feats)
    values = np.array([[1.0, 0.5, 2.0, -1.0]])
    cols = ["day_of_week_mon", "day_of_week_tue", "regular_patients", "is_monday"]
    out = to_feature_space(values, cols, feats)
    assert out.iloc[0].to_dict() == {"day_of_week": 1.5, "regular_patients": 2.0, "is_monday": -1.0}


def test_global_importance_and_direction(explainer: Explainer, X: pd.DataFrame) -> None:
    imp = explainer.global_importance(X.head(300))
    assert len(imp) == 10
    assert [g["mean_abs_shap"] for g in imp] == sorted(
        (g["mean_abs_shap"] for g in imp), reverse=True
    )
    direction = explainer.direction_check(X.head(300))
    assert set(direction) == set(STAFFING)
    # Monotone constraints: more staff never pushes the contribution up.
    assert all(v["slope"] <= 1e-9 for v in direction.values())


def test_direction_slope_catches_a_flipped_staffing_effect(ctx: FeatureContext) -> None:
    from sg_ml.features import add_features
    from sg_ml.models import hgb_regressor

    flipped = synthetic_rows(n_seq=15, seed=3, invert_staffing=True)
    F = add_features(flipped, ctx)
    names = list(FEATURE_SETS["full"])
    Xf = build_matrix(F, names)
    # Without constraints the model learns the inverted effect; the slope check sees it.
    model = hgb_regressor(names, FAST_PARAMS, 1)
    model.set_params(model__monotonic_cst=None)
    model.fit(Xf, F["ot_labor_hours"].astype(float))
    slopes = Explainer(model, names).direction_check(Xf)
    assert max(v["slope"] for v in slopes.values()) > 0


@pytest.mark.parametrize("sign", ["pos", "neg"])
def test_every_feature_has_a_sentence(sign: str) -> None:
    for name in FEATURE_SETS["full"]:
        assert REGISTRY[name].known_at_7am
        assert sign in dtx.TEMPLATES[name], name
    assert sign in dtx.TEMPLATES[OTHER]


def test_en_json_matches_templates() -> None:
    en = json.loads((ROOT / "apps/web/src/messages/en.json").read_text(encoding="utf-8"))
    assert en["drivers"] == dtx.TEMPLATES


def test_sentences() -> None:
    key, params, text = dtx.sentence("sterilizers_up", 1.0, 1.24)
    assert key == "drivers.sterilizers_up.pos"
    assert params == {"hours": 1.2, "value": 1}
    assert text == "Only 1 sterilizer available is adding about 1.2 hours"
    _, _, two = dtx.sentence("sterilizers_up", 2.0, 0.5)
    assert two == "2 sterilizers available is adding about 0.5 hours"
    _, _, neg = dtx.sentence("aft_11_staff", 3.0, -2.04)
    assert neg == "3 staff starting at 11:00 is reducing overtime by about 2 hours"
    _, p, day = dtx.sentence("day_of_week", "wed", 0.3)
    assert p["value"] == "Wednesday" and day.startswith("The Wednesday schedule")
    _, _, other = dtx.sentence(OTHER, None, -0.05)
    assert other == "Other factors is reducing overtime by about 0.1 hours"
    with pytest.raises(KeyError):
        dtx.sentence("not_a_feature", 1, 1.0)


def test_version_format() -> None:
    now = dt.datetime(2026, 10, 26, 0, 30, tzinfo=dt.UTC)
    assert make_version(now, "abc1234def") == "20261026-0030-abc1234"


class FakeBackend:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.rows: list[dict[str, Any]] = []

    def upload(self, path: str, data: bytes, content_type: str) -> None:
        assert path not in self.objects
        self.objects[path] = data

    def insert(self, row: dict[str, Any]) -> dict[str, Any]:
        self.rows.append(row)
        return {
            "version": row["version"],
            "status": "candidate",
            "gates_passed": row["gates_passed"],
        }

    def activate(self, version: str, actor: str | None) -> dict[str, Any]:
        raise NotImplementedError

    def rollback(self, feature_set: str, actor: str | None) -> dict[str, Any]:
        raise NotImplementedError

    def list(self) -> list[dict[str, Any]]:
        return self.rows


def test_register_uploads_artifact_and_card(result: TrainResult, tmp_path: Path) -> None:
    run_dir = save_run(result, tmp_path / "runs", tmp_path / "reports")
    backend = FakeBackend()
    now = dt.datetime(2026, 10, 26, 0, 30, tzinfo=dt.UTC)
    reg = register(run_dir, backend, sha="abc1234", now=now)
    assert reg.version == "20261026-0030-abc1234"
    assert set(backend.objects) == {
        f"{reg.version}/artifact.joblib",
        f"{reg.version}/model_card.json",
    }
    card = json.loads(backend.objects[f"{reg.version}/model_card.json"])
    for key in (
        "version",
        "datasets",
        "feature_set",
        "hyperparameters",
        "metrics",
        "thresholds",
        "thresholds_source",
        "intended_use",
        "limitations",
        "shap_global_top10",
    ):
        assert key in card, key
    assert card["thresholds_source"] == "simulated_provisional"
    assert len(card["shap_global_top10"]) == 10
    row = backend.rows[0]
    assert row["gates_passed"] is False  # candidates start ungated until SG-17 evaluates them
    assert row["artifact_path"] == f"{reg.version}/artifact.joblib"


def test_build_card_carries_gates(result: TrainResult) -> None:
    run = {
        **result.run,
        "gates": [{"name": "beats_baselines", "passed": True}],
        "gates_passed": True,
    }
    card = build_card(run, "v", "2026-10-26T00:30:00+00:00")
    assert card["gates_passed"] is True and card["gates"][0]["name"] == "beats_baselines"
