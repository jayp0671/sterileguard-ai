"""SG-09 simulator tests (Carlos extends these in SG-12). Synthetic inputs, fixed seeds."""

from __future__ import annotations

import datetime as dt
import itertools
import time
from collections import deque
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
import simpy

from sg_sim import calibrate as cal
from sg_sim.__main__ import main as sim_main
from sg_sim.config import SimConfig, load_config
from sg_sim.dataset import _actual_rows, _plan_rows, build_dataset, lhs_staffing, write_parquet
from sg_sim.export import content_hash, to_csv_bytes, to_frame, validate
from sg_sim.model import Floor, Unit, _take_load, machine
from sg_sim.run import (
    DayInputs,
    backlog_scale,
    overtime_hours,
    simulate_day,
    simulate_sequence,
)

CFG = load_config()
DAY = dt.date(2026, 10, 20)


def inputs(**over: Any) -> DayInputs:
    base: dict[str, Any] = dict(
        date=DAY,
        regular_patients=360,
        morning_staff_present=3,
        mf_cases=20,
        student_clinic_sessions=4,
        aft_11_staff=3,
        aft_13_staff=1,
        aft_15_staff=2,
        outside_support_staff=2,
        ot_available_staff=0,
        washers_up=2,
        sterilizers_up=2,
        carryover_backlog_estimate=1,
        is_holiday=False,
        academic_event="none",
    )
    base.update(over)
    return DayInputs(**base)


def cfg_with(**paths: Any) -> SimConfig:
    data = CFG.model_dump()
    for path, value in paths.items():
        node = data
        *head, leaf = path.split("__")
        for part in head:
            node = node[part]
        node[leaf] = value
    return SimConfig.model_validate(data)


def staff_at(result: Any, t: float) -> int:
    return sum(1 for _, s, e in result.log.presence.values() if s <= t < e)


def test_staff_pool_capacity_at_key_times() -> None:
    r = simulate_day(inputs(), CFG, np.random.default_rng(1))
    assert staff_at(r, -1) == 0  # 06:59
    assert staff_at(r, 0) == 3  # 07:00 morning
    assert staff_at(r, 240) == 6  # 11:00 morning + aft_11
    assert staff_at(r, 480) == 8  # 15:00 morning gone; aft_11, aft_13, aft_15, outside
    assert staff_at(r, 780) == 3  # 20:00 outside support gone at 20:00, aft_11 at 19:00


def test_no_task_outside_presence() -> None:
    r = simulate_day(inputs(ot_available_staff=2), CFG, np.random.default_rng(2))
    for wid, start, end in r.log.tasks:
        _, s, e = r.log.presence[wid]
        assert s <= start and end <= e + 1e-9


def test_overtime_hand_built_case() -> None:
    # stayers leave at 17:00, 18:00 and 20:00 -> 2 + 3 + 5 = 10 hours
    assert overtime_hours([600, 660, 780], 480) == pytest.approx(10.0)
    assert overtime_hours([400, 480], 480) == 0.0


def test_only_morning_stayers_count() -> None:
    r = simulate_day(inputs(ot_available_staff=0), CFG, np.random.default_rng(3))
    assert r.ot_labor_hours == 0.0
    r = simulate_day(inputs(ot_available_staff=2), CFG, np.random.default_rng(3))
    assert len(r.log.stayer_leaves) == 2
    assert r.ot_labor_hours == pytest.approx(overtime_hours(r.log.stayer_leaves, 480), abs=0.01)
    assert all(t <= CFG.clock.ot_cutoff + CFG.clock.cutoff_jitter for t in r.log.stayer_leaves)


@pytest.mark.parametrize("seed", [1, 2, 3, 4])
def test_conservation(seed: int) -> None:
    r = simulate_day(inputs(regular_patients=500), CFG, np.random.default_rng(seed))
    assert r.arrived_units == r.completed_units + r.end_backlog_units
    assert r.end_backlog_units == len(r.carryover)


def test_batch_take_respects_capacity() -> None:
    q = deque(Unit(i, "cassette", "wash", 1.0) for i in range(50))
    batch = _take_load(q, 40)
    assert len(batch) == 40 and len(q) == 10
    heavy = deque([Unit(0, "mf_tray", "wash", 60.0)])
    assert len(_take_load(heavy, 40)) == 1  # a single oversize unit still runs alone


def _machine_env(n_units: int, windows: list[tuple[float, float]] | None = None) -> Floor:
    env = simpy.Environment()
    floor = Floor(env, CFG, np.random.default_rng(0))
    for _ in range(n_units):
        floor.arrive("cassette", "wash")
    env.process(machine(env, floor, "wash", 0, windows or []))
    env.run(until=200)
    return floor


def test_machine_waits_for_fuller_load() -> None:
    small = _machine_env(1)
    assert small.log.cycles[0][2] == pytest.approx(CFG.machines.washer.max_load_wait)
    full = _machine_env(45)
    assert full.log.cycles[0][2] == 0.0
    assert full.log.cycles[0][4] <= CFG.machines.washer.capacity


def test_machine_never_runs_during_downtime() -> None:
    floor = _machine_env(45, windows=[(10.0, 100.0)])
    for _, _, s, e, _ in floor.log.cycles:
        assert e <= 10.0 or s >= 100.0


def test_machines_in_use_never_exceed_working_count() -> None:
    cfg = cfg_with(disruptions__p_down=1.0)
    r = simulate_day(inputs(washers_up=1, sterilizers_up=2), cfg, np.random.default_rng(5))
    for kind, limit in (("washer", 1), ("sterilizer", 2)):
        cycles = [(s, e) for k, _, s, e, _ in r.log.cycles if k == kind]
        for s, _ in cycles:
            assert sum(1 for s2, e2 in cycles if s2 <= s < e2) <= limit
    for stage, idx, ds, de in r.log.downtime:
        kind = "washer" if stage == "wash" else "sterilizer"
        for k, i, s, e, _ in r.log.cycles:
            if k == kind and i == idx:
                assert e <= ds or s >= de
    assert r.equipment_downtime_minutes > 0


def test_carryover_chains_between_days() -> None:
    days = simulate_sequence(6, dt.date(2026, 10, 19), CFG, 7)
    assert [d.date.weekday() for d in days] == [0, 1, 2, 3, 4, 0]  # weekends skipped
    for prev, nxt in itertools.pairwise(days):
        assert nxt.inputs.carryover_backlog_estimate == backlog_scale(prev.end_backlog_units, CFG)
        assert nxt.arrived_units >= prev.end_backlog_units


def test_reproducible_and_seed_sensitive() -> None:
    def csv(seed: int) -> bytes:
        res = simulate_sequence(5, DAY, CFG, seed)
        return to_csv_bytes(to_frame(res, "00000000-0000-4000-8000-000000000003"))

    assert csv(11) == csv(11)
    assert csv(11) != csv(12)


def test_one_day_is_fast() -> None:
    rng = np.random.default_rng(9)
    t = time.perf_counter()
    for _ in range(5):
        simulate_day(inputs(), CFG, rng)
    assert (time.perf_counter() - t) / 5 < 0.5


def test_export_validates_against_schema() -> None:
    df = validate(to_frame(simulate_sequence(5, DAY, CFG, 1), "dept", None))
    assert (df["source"] == "simulated").all()
    assert len(content_hash(df)) == 64


def test_lhs_design_within_bounds() -> None:
    rows = lhs_staffing(CFG, 200, 1)
    for row in rows:
        for key, (lo, hi) in CFG.design.items():
            if key.startswith("ot_available"):
                assert 0 <= row[key] <= row["morning_staff_present"]
            else:
                assert lo <= row[key] <= hi


def test_build_dataset_and_rows(tmp_path: Path) -> None:
    df, meta = build_dataset(CFG, 25, 3, workers=1)
    assert meta["row_count"] == 25 == len(df)
    assert df["date"].is_unique
    _df2, meta2 = build_dataset(CFG, 25, 3, workers=1)
    assert meta2["content_hash"] == meta["content_hash"]
    assert meta2["id"] == meta["id"]
    assert write_parquet(df, meta, tmp_path).exists()
    cols, rows = _plan_rows(df)
    assert "plan_date" in cols and len(rows) == 25
    assert all(r[cols.index("mf_cases__missing")] is False for r in rows)
    cols, rows = _actual_rows(df)
    assert "shift_date" in cols and len(rows) == 25


def test_calibration_smoke(tmp_path: Path) -> None:
    real = [(inputs(), 6.0), (inputs(date=dt.date(2026, 10, 21), regular_patients=420), 9.0)]
    best, ev = cal.calibrate(CFG, real, trials=2, reps=2, seed=1)
    assert set(best) == set(cal.FREE_PARAMS)
    assert ev.mae is not None and ev.loss >= ev.mae
    out = tmp_path / "cal.yaml"
    cal.write_calibrated(CFG, best, out)
    assert load_config(out).scale.stage_time == pytest.approx(best["stage_time"])
    assert cal.write_report(ev, best, len(real), tmp_path).exists()


def test_real_csv_loading_and_validation(tmp_path: Path) -> None:
    df = to_frame(simulate_sequence(6, DAY, CFG, 2), "dept")
    df["source"] = "real"
    path = tmp_path / "real.csv"
    df.assign(date=df["date"].dt.strftime("%Y-%m-%d")).to_csv(path, index=False)
    real = cal.load_real(path, None, CFG.department_settings)
    assert len(cal.real_inputs(real)) == 6
    assert cal.load_real(None, None, {}).empty
    report = cal.ks_validate(df, real, tmp_path)
    assert "KS statistic" in report.read_text()
    assert "need at least 5" in cal.ks_validate(df, real.head(2), tmp_path).read_text()


def test_cli_run_without_upload(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import sg_sim.__main__ as entry

    monkeypatch.setattr(entry, "ROOT", tmp_path)
    monkeypatch.delenv("SG_SIM_DB_URL", raising=False)
    assert sim_main(["run", "--days", "20", "--seed", "1", "--workers", "1", "--no-upload"]) == 0
    assert list((tmp_path / "data" / "sim").glob("*.parquet"))


def test_config_hash_is_stable() -> None:
    assert load_config().config_hash == CFG.config_hash
    assert cfg_with(scale__stage_time=0.9).config_hash != CFG.config_hash


def test_frame_has_schema_columns() -> None:
    from sg_data.schema import FIELDS

    df = to_frame(simulate_sequence(2, DAY, CFG, 1), "dept")
    assert list(df.columns) == [f.name for f in FIELDS]
    assert isinstance(df, pd.DataFrame)
