"""Feature registry and leakage guard (SG-13)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from sg_data.schema import FIELDS, TIER2_INPUTS
from sg_ml import features as fx
from sg_ml.data import CALIBRATED, config_for
from sg_sim.config import load_config

UNSAFE = [f.name for f in FIELDS if f.role == "outcome" or f.tier == 3]


def test_every_schema_input_is_registered_and_safe() -> None:
    for f in FIELDS:
        if f.role == "input" and f.name != "date":
            assert fx.REGISTRY[f.name].known_at_7am
            assert fx.REGISTRY[f.name].monotone == f.monotone


@pytest.mark.parametrize("feature_set", sorted(fx.FEATURE_SETS))
@pytest.mark.parametrize("unsafe", UNSAFE)
def test_build_matrix_rejects_outcome_or_tier3(
    rows: pd.DataFrame, ctx: fx.FeatureContext, feature_set: str, unsafe: str
) -> None:
    F = fx.add_features(rows.head(40), ctx)
    with pytest.raises(fx.LeakageError):
        fx.build_matrix(F, [*fx.FEATURE_SETS[feature_set], unsafe])


def test_build_matrix_rejects_unregistered_and_unknown_at_7am(
    rows: pd.DataFrame, ctx: fx.FeatureContext
) -> None:
    F = fx.add_features(rows.head(40), ctx)
    F["end_backlog_units"] = 1.0
    with pytest.raises(fx.LeakageError, match="not in the feature registry"):
        fx.build_matrix(F, [*fx.FEATURE_SETS["full"], "end_backlog_units"])
    fx.REGISTRY["late_flag"] = fx.Feature("late_flag", "numeric", "engineered", False)
    try:
        F["late_flag"] = 0.0
        with pytest.raises(fx.LeakageError, match="not known at 7:00 AM"):
            fx.build_matrix(F, ["regular_patients", "late_flag"])
    finally:
        del fx.REGISTRY["late_flag"]


def test_feature_sets_are_all_safe() -> None:
    for names in fx.FEATURE_SETS.values():
        assert len(fx.check_features(names)) == len(names)
    assert set(fx.FEATURE_SETS["core"]) < set(fx.FEATURE_SETS["full"])
    assert "patients_per_morning_staff" in fx.FEATURE_SETS["core"]
    assert not any(n.endswith("__missing") for n in fx.FEATURE_SETS["core"])


def test_context_reads_coefficients_from_config() -> None:
    cfg = load_config(CALIBRATED)
    ctx = fx.FeatureContext.from_config(cfg)
    assert ctx.window_hours_before_15 == {"aft_11": 4.0, "aft_13": 2.0, "aft_15": 0.0}
    assert ctx.morning_hours_before_15 == 8.0
    assert ctx.outside_support_hours_before_15 == pytest.approx(3.0)
    bigger = cfg.model_copy(deep=True)
    bigger.scale.units_per_patient *= 2
    assert fx.FeatureContext.from_config(bigger).units_per_patient == pytest.approx(
        2 * ctx.units_per_patient
    )
    assert config_for({"config_hash": cfg.config_hash}).config_hash == cfg.config_hash


def test_engineered_values_by_hand(rows: pd.DataFrame, ctx: fx.FeatureContext) -> None:
    F = fx.add_features(rows.head(5), ctx)
    r = F.iloc[0]
    hours = (
        r.morning_staff_present * 8
        + r.aft_11_staff * 4
        + r.aft_13_staff * 2
        + r.outside_support_staff * ctx.outside_support_hours_before_15
    )
    assert r.staff_hours_before_15 == pytest.approx(hours)
    assert r.total_afternoon_staff == r.aft_11_staff + r.aft_13_staff + r.aft_15_staff
    assert r.patients_per_morning_staff == pytest.approx(
        r.regular_patients / max(r.morning_staff_present, 1)
    )
    demand = (
        r.regular_patients * ctx.units_per_patient
        + r.mf_cases * ctx.units_per_mf_case
        + r.student_clinic_sessions * ctx.units_per_session
    )
    assert r.demand_units_est == pytest.approx(demand)
    assert r.capacity_ratio == pytest.approx(demand / hours)
    assert r.day_of_week == "mon" and r.is_monday and not r.is_friday
    for n in TIER2_INPUTS:
        assert F[f"{n}__missing"].eq(False).all()


def test_missing_tier2_is_filled_and_flagged(rows: pd.DataFrame, ctx: fx.FeatureContext) -> None:
    df = rows.head(3).copy()
    df["mf_cases"] = df["mf_cases"].astype(object)
    df.loc[df.index[0], "mf_cases"] = None
    F = fx.add_features(df, ctx, {"mf_cases_default": 17})
    assert F.loc[df.index[0], "mf_cases"] == 17
    assert bool(F.loc[df.index[0], "mf_cases__missing"])
    assert not F.loc[df.index[1], "mf_cases__missing"]


def test_lags_use_only_strictly_earlier_days(rows: pd.DataFrame, ctx: fx.FeatureContext) -> None:
    df = rows.head(40).copy()  # two sequences
    F = fx.add_features(df, ctx)
    # First day of each sequence has no history.
    seq = fx.sequence_ids(df)
    firsts = df.groupby(seq)["date"].idxmin()
    assert F.loc[firsts, "ot_hours_prev_day"].isna().all()
    # Monday looks back over the weekend to Friday.
    mon = df.index[5]
    assert pd.Timestamp(df.loc[mon, "date"]).weekday() == 0
    assert F.loc[mon, "ot_hours_prev_day"] == df.loc[df.index[4], "ot_labor_hours"]
    # 7-day mean: the five workdays before the 2nd Monday (Mon-Fri of week 1 minus none).
    window = df.loc[df.index[0:5], "ot_labor_hours"].mean()
    assert F.loc[mon, "ot_hours_7d_mean"] == pytest.approx(window)
    # Changing today's or a later day's outcome never changes today's lags.
    mutated = df.copy()
    mutated.loc[df.index[10:], "ot_labor_hours"] = 99.0
    G = fx.add_features(mutated, ctx)
    cols = ["ot_hours_prev_day", "ot_hours_7d_mean"]
    pd.testing.assert_frame_equal(F.loc[df.index[:11], cols], G.loc[df.index[:11], cols])


def test_lags_never_cross_sequences(rows: pd.DataFrame, ctx: fx.FeatureContext) -> None:
    F = fx.add_features(rows.head(40), ctx)
    assert np.isnan(F.iloc[20]["ot_hours_7d_mean"])


def test_week_of_semester() -> None:
    dates = pd.Series(pd.to_datetime(["2026-09-02", "2026-09-09", "2026-01-05", "2026-01-20"]))
    weeks = fx.week_of_semester(dates, ("01-20", "05-26", "09-02"))
    assert weeks.tolist() == [1, 2, 18, 1]


def test_build_matrix_types(rows: pd.DataFrame, ctx: fx.FeatureContext) -> None:
    F = fx.add_features(rows.head(25), ctx)
    X = fx.build_matrix(F, "full")
    assert list(X.columns) == list(fx.FEATURE_SETS["full"])
    for name in X.columns:
        if fx.REGISTRY[name].kind == "categorical":
            assert pd.api.types.is_string_dtype(X[name]), name
        else:
            assert X[name].dtype == np.float64, name


def test_staffing_list_matches_schema_directions() -> None:
    assert "morning_staff_present" in fx.STAFFING
    assert "ot_available_staff" not in fx.STAFFING
    assert all(fx.REGISTRY[n].monotone == -1 for n in fx.STAFFING)
