"""Demo history and forecasts are deterministic (SG-16)."""

from __future__ import annotations

import datetime as dt

import pandas as pd

from sg_ml import demo
from sg_ml.data import CALIBRATED
from sg_ml.registry import load_artifact
from sg_ml.testing import tiny_artifact_bytes
from sg_sim.config import load_config

TODAY = dt.date(2026, 10, 26)  # a Monday
DEPT = "00000000-0000-4000-8000-000000000003"


def test_demo_workdays_skip_weekends_and_today() -> None:
    days = demo.demo_workdays(TODAY, 10)
    assert days[-1] == dt.date(2026, 10, 23)  # the Friday before
    assert all(d.weekday() < 5 and d < TODAY for d in days)
    assert days[0] == dt.date(2026, 10, 16) and len(days) == 6


def test_history_and_forecasts_are_reproducible() -> None:
    cfg = load_config(CALIBRATED)
    a = demo.history(cfg, TODAY, DEPT, days=8)
    b = demo.history(cfg, TODAY, DEPT, days=8)
    pd.testing.assert_frame_equal(a, b)
    assert (a["source"] == "simulated").all()
    assert a["dataset_id"].nunique() == 1

    artifact = load_artifact(tiny_artifact_bytes(7))
    f1, d1 = demo.forecasts(a, artifact, "v-test", None)
    f2, d2 = demo.forecasts(b, artifact, "v-test", None)
    assert f1 == f2 and d1 == d2
    first = f1[0]
    assert first["id"] == demo.demo_id("forecast", DEPT, first["target_date"])
    assert first["created_at"].startswith(
        (dt.date.fromisoformat(first["target_date"]) - dt.timedelta(days=1)).isoformat()
    )
    assert first["ot_p10"] <= first["ot_p50"] <= first["ot_p90"]
    assert {d["forecast_id"] for d in d1} == {f["id"] for f in f1}
