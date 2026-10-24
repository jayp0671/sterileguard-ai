"""SG-12 part A: simulator correctness. Property tests use the repo Hypothesis profile
(HYPOTHESIS_PROFILE=ci in CI: 50 derandomized examples). Synthetic inputs only."""

from __future__ import annotations

import datetime as dt
import statistics
import time
from typing import Any

import numpy as np
import pandas.testing as pdt
import pytest
from hypothesis import given
from hypothesis import strategies as st

from sg_sim.config import SimConfig, load_config
from sg_sim.export import content_hash, to_frame
from sg_sim.model import CarryUnit
from sg_sim.run import DayInputs, DayResult, simulate_day, simulate_sequence

CFG = load_config()
DAY = dt.date(2026, 10, 20)


def day_inputs(**over: Any) -> DayInputs:
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
        ot_available_staff=2,
        washers_up=2,
        sterilizers_up=2,
        carryover_backlog_estimate=1,
        is_holiday=False,
        academic_event="none",
    )
    base.update(over)
    return DayInputs(**base)


@st.composite
def valid_inputs(draw: st.DrawFn) -> DayInputs:
    morning = draw(st.integers(1, 5))
    return day_inputs(
        regular_patients=draw(st.integers(0, 600)),
        morning_staff_present=morning,
        ot_available_staff=draw(st.integers(0, morning)),
        mf_cases=draw(st.integers(0, 40)),
        student_clinic_sessions=draw(st.integers(0, 10)),
        aft_11_staff=draw(st.integers(0, 4)),
        aft_13_staff=draw(st.integers(0, 2)),
        aft_15_staff=draw(st.integers(0, 3)),
        outside_support_staff=draw(st.integers(0, 3)),
        washers_up=draw(st.integers(0, 2)),
        sterilizers_up=draw(st.integers(0, 2)),
        carryover_backlog_estimate=draw(st.integers(0, 2)),
    )


def staff_counts(r: DayResult) -> list[int]:
    """Head count after every arrival or departure, in time order."""
    events = sorted(
        [(s, 1) for _, s, _ in r.log.presence.values()]
        + [(e, -1) for _, _, e in r.log.presence.values()],
        key=lambda x: (x[0], x[1]),
    )
    out, n = [], 0
    for _, delta in events:
        n += delta
        out.append(n)
    return out


# --- properties ----------------------------------------------------------------------------


@given(valid_inputs(), st.integers(0, 2**31 - 1))
def test_conservation_and_bounds(inputs: DayInputs, seed: int) -> None:
    r = simulate_day(inputs, CFG, np.random.default_rng(seed))
    # conservation: every unit that arrived is completed or carried over
    assert r.arrived_units == r.completed_units + r.end_backlog_units
    # overtime bounds: only stayers count, and nobody stays past their personal cutoff
    latest = CFG.clock.ot_cutoff + CFG.clock.cutoff_jitter
    max_ot = inputs.ot_available_staff * (latest - CFG.clock.morning_end) / 60
    assert 0 <= r.ot_labor_hours <= max_ot + 1e-9
    # the staff pool never goes negative
    assert min(staff_counts(r), default=0) >= 0
    # nobody works outside their presence
    for wid, start, end in r.log.tasks:
        _, s, e = r.log.presence[wid]
        assert s <= start and end <= e + 1e-9
    # machines in use never exceed the working count, and never run during downtime
    for kind, limit in (("washer", inputs.washers_up), ("sterilizer", inputs.sterilizers_up)):
        cycles = [(s, e) for k, _, s, e, _ in r.log.cycles if k == kind]
        for s, _ in cycles:
            assert sum(1 for s2, e2 in cycles if s2 <= s < e2) <= limit
    for stage, idx, ds, de in r.log.downtime:
        kind = "washer" if stage == "wash" else "sterilizer"
        for k, i, s, e, _ in r.log.cycles:
            if k == kind and i == idx:
                assert e <= ds or s >= de


# --- reproducibility -----------------------------------------------------------------------


def _frame(seed: int) -> Any:
    return to_frame(simulate_sequence(8, DAY, CFG, seed), "00000000-0000-4000-8000-000000000003")


def test_same_seed_same_frame_and_hash() -> None:
    a, b = _frame(5), _frame(5)
    pdt.assert_frame_equal(a, b)
    assert content_hash(a) == content_hash(b)


def test_different_seed_changes_output() -> None:
    assert content_hash(_frame(5)) != content_hash(_frame(6))


# --- golden scenario -----------------------------------------------------------------------


def golden_config() -> SimConfig:
    """Tiny deterministic department: fixed stage and cycle times, no disruptions."""
    data = CFG.model_dump()
    const = lambda v: {"dist": "const", "value": v}  # noqa: E731
    for unit in data["units"].values():
        unit.update(decon=const(10), inspect=const(10), pack=const(10), weight=1.0)
    data["machines"]["washer"].update(capacity=40, cycle=const(300), max_load_wait=0)
    data["machines"]["sterilizer"].update(capacity=40, cycle=const(295), max_load_wait=0)
    data["machines"]["cool_minutes"] = 0
    data["disruptions"].update(p_down=0.0, p_bi=0.0)
    data["work"].update(emergency_patients=const(0), unused_factor=const(1))
    data["clock"]["cutoff_jitter"] = 0
    data["staff"]["ot_stay_threshold"] = 1.0
    data["scale"] = {"units_per_patient": 1.0, "units_per_session": 1.0, "stage_time": 1.0}
    return SimConfig.model_validate(data)


def test_golden_scenario_overtime_by_hand() -> None:
    """2 morning staff (both willing to stay), 1 washer, 1 sterilizer, 4 cassettes waiting.

    07:00  both decontaminate units 0,1 (10 min), then units 2,3 (10 min)
    washer: units 0,1 from t=10 to 310; units 2,3 from 310 to 610
    units 0,1: inspect 310-320, pack 320-330, sterilize 330-625
    units 2,3: inspect 610-620, pack 620-630
    At 630 two units remain. Stayers decide one at a time: the first sees 2 units for 2 staff
    (1 per person <= threshold 1) and leaves; the second then sees 2 units for 1 person (> 1),
    stays, and leaves at the 21:00 cutoff (t = 840) while units 2,3 sterilize until 925.
    Overtime = (630 - 480) + (840 - 480) = 510 min = 8.5 h.
    """
    cfg = golden_config()
    inputs = day_inputs(
        regular_patients=0,
        mf_cases=0,
        student_clinic_sessions=0,
        morning_staff_present=2,
        ot_available_staff=2,
        aft_11_staff=0,
        aft_13_staff=0,
        aft_15_staff=0,
        outside_support_staff=0,
        washers_up=1,
        sterilizers_up=1,
    )
    carry = [CarryUnit("cassette", "decon") for _ in range(4)]
    r = simulate_day(inputs, cfg, np.random.default_rng(0), carryover=carry)
    assert r.log.stayer_leaves == [630.0, 840.0]
    assert r.ot_labor_hours == 8.5
    assert [(k, s, e) for k, _, s, e, _ in r.log.cycles] == [
        ("washer", 10.0, 310.0),
        ("washer", 310.0, 610.0),
        ("sterilizer", 330.0, 625.0),
        ("sterilizer", 630.0, 925.0),
    ]
    assert r.completed_units == 4 and r.end_backlog_units == 0


# --- directional sanity (statistical) ------------------------------------------------------


def _mean_ot(cfg: SimConfig, reps: int, **over: Any) -> tuple[float, float]:
    rng = np.random.default_rng(123)
    ots = [simulate_day(day_inputs(**over), cfg, rng).ot_labor_hours for _ in range(reps)]
    return statistics.fmean(ots), statistics.stdev(ots) / reps**0.5


@pytest.mark.slow
def test_more_morning_staff_never_raises_overtime() -> None:
    base, se_base = _mean_ot(CFG, 50, regular_patients=420, morning_staff_present=3)
    more, se_more = _mean_ot(CFG, 50, regular_patients=420, morning_staff_present=4)
    assert more <= base + 2 * (se_base**2 + se_more**2) ** 0.5


@pytest.mark.slow
def test_sterilizer_down_raises_overtime() -> None:
    both, _ = _mean_ot(CFG, 50, regular_patients=420)
    one, _ = _mean_ot(CFG, 50, regular_patients=420, sterilizers_up=1)
    assert one > both


@pytest.mark.slow
def test_hundred_days_under_a_minute() -> None:
    start = time.perf_counter()
    simulate_sequence(100, DAY, CFG, 1)
    assert time.perf_counter() - start < 60
