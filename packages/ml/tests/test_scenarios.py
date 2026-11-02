"""Staffing scenario engine (SG-19). Synthetic data only; the model is the tiny trained
artifact, so the served p50 is the monotone squared-error pipeline (ADR-0005)."""

from __future__ import annotations

import io
import itertools
import time
from typing import Any

import joblib
import numpy as np
import pandas as pd
import pytest

from sg_ml import scenarios as sc
from sg_ml.features import F, FeatureContext, add_features, build_matrix
from sg_ml.models import CLASSES
from sg_ml.testing import feature_row, tiny_artifact_bytes

SETTINGS: dict[str, Any] = {
    "shift_windows": [
        {"key": "morning", "start": "07:00", "end": "15:00"},
        {"key": "aft_11", "start": "11:00", "end": "19:00"},
        {"key": "aft_13", "start": "13:00", "end": "21:00"},
        {"key": "aft_15", "start": "15:00", "end": "23:00"},
    ],
    "outside_support_until": "20:00",
}


@pytest.fixture(scope="module")
def artifact() -> dict[str, Any]:
    out: dict[str, Any] = joblib.load(io.BytesIO(tiny_artifact_bytes()))
    return out


def plan(seed: int, morning: int = 3) -> dict[str, Any]:
    row = feature_row(seed)
    row[F.morning_staff_present] = morning
    row[F.ot_available_staff] = min(int(row[F.ot_available_staff]), morning)
    return row


def run(artifact: dict[str, Any], row: dict[str, Any], **kw: Any) -> sc.ScenarioResult:
    return sc.evaluate(artifact, row, SETTINGS, model_version="test", **kw)


def test_window_hours_follow_department_settings(artifact: dict[str, Any]) -> None:
    ctx = FeatureContext.from_dict(artifact["context"])
    hours = sc.window_hours(SETTINGS, ctx)
    assert hours[F.morning_staff_present] == 8
    assert hours[F.aft_11_staff] == 4
    assert hours[F.aft_13_staff] == 2
    # Outside support starts at noon in the simulator config and stays until 20:00.
    assert hours[F.outside_support_staff] == 8
    assert hours[F.ot_available_staff] == 0


def test_default_grid_and_costs(artifact: dict[str, Any]) -> None:
    row = plan(7)
    res = run(artifact, row)
    # 3^4 staff combinations x volunteers 0..3 (never more than the morning staff count)
    assert len(res.options) == 81 * 4
    assert res.base.changes == dict.fromkeys(sc.LEVERS, 0)
    assert res.base.added_staff_hours == 0
    one = next(
        o for o in res.options if o.id == f"m+1.a11+1.a13+0.os+0.v{row[F.ot_available_staff]}"
    )
    assert one.added_staff_hours == 8 + 4
    assert res.disclaimer == "Model estimate, not a guarantee."
    assert len({o.id for o in res.options}) == len(res.options)


def p50_of(res: sc.ScenarioResult) -> dict[tuple[int, ...], float]:
    return {tuple(o.values[k] for k in sc.LEVERS): o.ot_p50 for o in res.options}


@pytest.mark.parametrize("seed", [1, 7, 11])
def test_adding_staff_never_raises_p50(artifact: dict[str, Any], seed: int) -> None:
    res = run(artifact, plan(seed))
    table = p50_of(res)
    checked = 0
    for key, p50 in table.items():
        for j in range(len(sc.STAFF_LEVERS)):
            bumped = list(key)
            bumped[j] += 1
            if tuple(bumped) in table:
                assert table[tuple(bumped)] <= p50 + 1e-9, (key, sc.STAFF_LEVERS[j])
                checked += 1
    assert checked > 100


def brute_force_minimum(
    artifact: dict[str, Any], row: dict[str, Any], target: sc.Target
) -> tuple[float, float] | None:
    """One prediction per option in a plain loop: the least added staff-hours (then the lowest
    p90) among in-support, non-what-if options that meet the target."""
    ctx = FeatureContext.from_dict(artifact["context"])
    hours = sc.window_hours(SETTINGS, ctx)
    support = sc.support_from_artifact(artifact)
    bounds = sc.default_bounds(row)
    best: tuple[float, float] | None = None
    for combo in itertools.product(*(range(lo, hi + 1) for lo, hi in bounds.values())):
        values = dict(zip(bounds, combo, strict=True))
        if values[sc.VOLUNTEER_LEVER] != row[sc.VOLUNTEER_LEVER]:
            continue
        if any(not support[k][0] <= v <= support[k][1] for k, v in values.items()):
            continue
        one = pd.DataFrame([{**row, **values}])
        X = build_matrix(add_features(one, ctx, SETTINGS, lags=False), artifact["feature_list"])
        band, probs = sc.predict_frame(artifact, X)
        p_high = probs[0, CLASSES.index("high")]
        if not target.met(band[:, 1], np.array([p_high]))[0]:
            continue
        cost = sum((values[k] - row[k]) * hours[k] for k in sc.STAFF_LEVERS)
        cand = (round(cost, 6), round(float(band[0, 2]), 6))
        best = cand if best is None or cand < best else best
    return best


@pytest.mark.parametrize("seed", [2, 5, 9, 13, 21])
def test_minimum_change_matches_brute_force(artifact: dict[str, Any], seed: int) -> None:
    row = plan(seed)
    base = run(artifact, row).base
    for target in (
        sc.Target("p50_hours", max(0.0, base.ot_p50 - 1.5)),
        sc.Target("p_high", 0.3),
    ):
        res = run(artifact, row, target=target)
        expected = brute_force_minimum(artifact, row, target)
        if expected is None:
            assert res.minimum_change_id is None
            continue
        chosen = res.option(res.minimum_change_id or "")
        assert chosen is not None
        assert (chosen.added_staff_hours, chosen.ot_p90) == pytest.approx(expected, abs=0.01)
        assert chosen.meets_target and not chosen.low_confidence and not chosen.what_if


def test_low_confidence_options_are_never_recommended(artifact: dict[str, Any]) -> None:
    row = plan(7)
    narrow = dict(artifact)
    # Training never saw more 11:00 staff than the plan has: every +1/+2 at 11:00 is unsupported.
    # Every other lever is widened to cover the whole grid.
    support = {k: (0.0, 20.0) for k in sc.LEVERS}
    support[F.aft_11_staff] = (0, float(row[F.aft_11_staff]))
    narrow["staffing_support"] = {k: list(v) for k, v in support.items()}
    res = run(narrow, row, target=sc.Target("p50_hours", 0.0))
    flagged = [o for o in res.options if o.changes[F.aft_11_staff] > 0]
    assert flagged and all(o.low_confidence for o in flagged)
    assert not any(o.low_confidence for o in res.options if o.changes[F.aft_11_staff] == 0)
    for oid in [*res.pareto_ids, res.minimum_change_id]:
        if oid:
            assert not res.option(oid).low_confidence  # type: ignore[union-attr]


def test_only_low_confidence_options_meet_the_target(artifact: dict[str, Any]) -> None:
    row = plan(7)
    res = run(artifact, row)
    best = min(o.ot_p50 for o in res.options if not o.what_if)
    narrow = dict(artifact)
    # Every staffing increase falls outside support, so nothing below the base can be chosen.
    narrow["staffing_support"] = {k: [0, row[k]] for k in sc.STAFF_LEVERS}
    target = sc.Target("p50_hours", (best + res.base.ot_p50) / 2)
    out = run(narrow, row, target=target)
    if res.base.ot_p50 > target.value:
        assert out.minimum_change_id is None
        assert out.message.startswith("Even with")


def test_volunteer_what_ifs_are_explored_but_not_recommended(artifact: dict[str, Any]) -> None:
    res = run(artifact, plan(7), target=sc.Target("p50_hours", 0.0))
    what_ifs = [o for o in res.options if o.what_if]
    volunteers_only = [o for o in what_ifs if not any(o.changes[k] for k in sc.STAFF_LEVERS)]
    # Changing only who is willing to stay adds no staff-hours.
    assert volunteers_only and all(o.added_staff_hours == 0 for o in volunteers_only)
    assert not {o.id for o in what_ifs} & {*res.pareto_ids, res.minimum_change_id}


def test_nothing_meets_target(artifact: dict[str, Any]) -> None:
    res = run(artifact, plan(7), target=sc.Target("p50_hours", -1))
    assert res.minimum_change_id is None
    assert res.message == (
        "Even with +2 staff in every window, predicted overtime stays above the target."
    )


def test_base_already_meets_target(artifact: dict[str, Any]) -> None:
    res = run(artifact, plan(7), target=sc.Target("p50_hours", 999))
    assert res.minimum_change_id == res.base.id
    assert res.message.startswith("Tomorrow's plan already meets the target")


def test_recommendation_message(artifact: dict[str, Any]) -> None:
    row = plan(7)
    base = run(artifact, row).base
    res = run(artifact, row, target=sc.Target("p50_hours", base.ot_p50 - 0.5))
    if res.minimum_change_id and res.minimum_change_id != res.base.id:
        assert res.message.startswith("Add ")
        assert "Predicted overtime drops from" in res.message
    assert sc.describe_changes({F.aft_11_staff: 1}) == "Add 1 staff starting at 11:00"
    assert sc.describe_changes({F.aft_11_staff: 1, F.outside_support_staff: 2}) == (
        "Add 1 staff starting at 11:00 and 2 outside support staff"
    )


def test_pareto_front_is_non_dominated(artifact: dict[str, Any]) -> None:
    res = run(artifact, plan(7))
    front = [res.option(i) for i in res.pareto_ids]
    assert front[0] is not None and front[0].added_staff_hours == 0
    eligible = [o for o in res.options if not o.low_confidence and not o.what_if]
    for f in front:
        assert f is not None
        assert not any(
            o.added_staff_hours <= f.added_staff_hours
            and o.ot_p50 < f.ot_p50 - 1e-9
            and o.id != f.id
            for o in eligible
        )


def test_default_target_uses_alert_threshold(artifact: dict[str, Any]) -> None:
    thresholds = list(artifact["thresholds"])
    assert sc.default_target({}, thresholds) == sc.Target("p50_hours", thresholds[1])
    assert sc.default_target({"alert_threshold_hours": 6}, thresholds).value == 6


def test_bounds_validation() -> None:
    row = plan(7)
    with pytest.raises(sc.ScenarioError, match="not a staffing lever"):
        sc.resolve_bounds(row, {"regular_patients": {"min": 0, "max": 1}})
    with pytest.raises(sc.ScenarioError, match="min <= max"):
        sc.resolve_bounds(row, {F.aft_11_staff: {"min": 3, "max": 1}})
    with pytest.raises(sc.ScenarioError, match="exceed the limit"):
        sc.resolve_bounds(row, {k: {"min": 0, "max": 9} for k in sc.STAFF_LEVERS})


def test_fixed_bounds_evaluate_one_option(artifact: dict[str, Any]) -> None:
    row = plan(7)
    fixed = {k: {"min": row[k] + 1, "max": row[k] + 1} for k in sc.STAFF_LEVERS}
    fixed[sc.VOLUNTEER_LEVER] = {"min": row[sc.VOLUNTEER_LEVER], "max": row[sc.VOLUNTEER_LEVER]}
    res = run(artifact, row, levers=fixed)
    # The one requested option plus the base, which is always evaluated.
    assert len(res.options) == 2


@pytest.mark.parametrize("morning", [2, 3])
def test_grid_is_fast(artifact: dict[str, Any], morning: int) -> None:
    row = plan(7, morning=morning)
    run(artifact, row)  # warm up
    start = time.perf_counter()
    res = run(artifact, row)
    elapsed = time.perf_counter() - start
    assert len(res.options) >= 243
    assert elapsed < 2.0


def test_training_stores_staffing_support(artifact: dict[str, Any]) -> None:
    support = artifact["staffing_support"]
    assert set(support) == set(sc.LEVERS)
    assert all(lo <= hi for lo, hi in support.values())
    assert sc.support_from_artifact(artifact)[F.morning_staff_present] == tuple(
        support[F.morning_staff_present]
    )


def test_older_artifacts_fall_back_to_the_background_sample(artifact: dict[str, Any]) -> None:
    old = {k: v for k, v in artifact.items() if k != "staffing_support"}
    support = sc.support_from_artifact(old)
    bg = artifact["explainer_background"]
    assert support[F.aft_11_staff] == (bg[F.aft_11_staff].min(), bg[F.aft_11_staff].max())
