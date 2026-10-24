"""simulate_day and simulate_sequence (SG-09).

Determinism: one numpy Generator is passed everywhere (never the global random state) and every
day gets a fresh SimPy Environment, so the same seed and config give identical output.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import simpy
from pydantic import BaseModel

from sg_data.defaults import default_for
from sg_data.schema import TIER2_INPUTS, to_pydantic
from sg_sim.config import SimConfig
from sg_sim.model import (
    STAFF_STAGES,
    CarryUnit,
    DayLog,
    Floor,
    arrivals,
    bi_recall,
    machine,
    monitor,
    worker,
)

_PlanIn: Any = to_pydantic("plan_in")


class DayInputs(_PlanIn):  # type: ignore[misc]
    """The schema's plan inputs plus the date. Same field names as sg_data, by construction."""

    date: dt.date

    @property
    def day_of_week(self) -> int:
        return self.date.weekday()


def complete_inputs(inputs: BaseModel, cfg: SimConfig) -> DayInputs:
    """Fill missing Tier 2 inputs from the config's department settings (never Tier 1)."""
    values = inputs.model_dump()
    for name in TIER2_INPUTS:
        if values.get(name) is None:
            values[name] = default_for(name, cfg.department_settings)
    return DayInputs(**values)


@dataclass
class DayResult:
    date: dt.date
    inputs: DayInputs
    ot_labor_hours: float
    end_backlog_units: int
    returned_unused_estimate: int
    emergency_intake_patients: int
    equipment_downtime_minutes: int
    last_completion_time: float
    arrived_units: int
    completed_units: int
    carryover: list[CarryUnit]
    log: DayLog = field(repr=False)

    def outcomes(self) -> dict[str, Any]:
        return {
            "ot_labor_hours": self.ot_labor_hours,
            "emergency_intake_patients": self.emergency_intake_patients,
            "returned_unused_estimate": self.returned_unused_estimate,
            "equipment_downtime_minutes": self.equipment_downtime_minutes,
        }


def overtime_hours(leave_times: list[float], morning_end: float) -> float:
    """Sum over morning stayers of (leave time - 15:00), in hours."""
    return sum(max(0.0, t - morning_end) for t in leave_times) / 60.0


def _poisson(rng: np.random.Generator, mean: float) -> int:
    return int(rng.poisson(max(mean, 0.0)))


def _pickups(cfg: SimConfig, rng: np.random.Generator, first: float, last: float) -> list[float]:
    times = [first]
    while True:
        nxt = times[-1] + cfg.arrivals.pickup_interval.sample(rng)
        if nxt > last:
            return times
        times.append(nxt)


def build_schedule(
    inputs: DayInputs, cfg: SimConfig, rng: np.random.Generator
) -> tuple[list[tuple[float, str, int]], int, int]:
    """Arrival schedule (time, unit kind, count), emergency patients and returned unused units."""
    w = cfg.work
    sched: list[tuple[float, str, int]] = []
    # Clinic work: regular patients plus used student-clinic sets, over each block's pickups.
    clinic: dict[str, int] = {
        kind: _poisson(rng, inputs.regular_patients * rate * cfg.scale.units_per_patient)
        for kind, rate in w.per_patient.items()
    }
    issued = _poisson(
        rng,
        inputs.student_clinic_sessions
        * w.per_session.get("cassette", 0)
        * cfg.scale.units_per_session,
    )
    unused_p = min(1.0, w.unused_share * w.unused_factor.sample(rng))
    unused = int(rng.binomial(issued, unused_p)) if issued else 0
    clinic["cassette"] = clinic.get("cassette", 0) + issued - unused
    for block in cfg.arrivals.blocks:
        times = _pickups(cfg, rng, block.first_pickup, block.last_pickup)
        for kind, total in clinic.items():
            n = int(rng.binomial(total, block.share))
            for t, c in zip(times, rng.multinomial(n, [1 / len(times)] * len(times)), strict=True):
                if c:
                    sched.append((t, kind, int(c)))
    # Maxillofacial cases: trays return about an hour after each case.
    lo, hi = cfg.arrivals.mf_case_window
    for case_t in rng.uniform(lo, hi, int(inputs.mf_cases)).tolist():
        for kind, rate in w.per_mf_case.items():
            sched.append((float(case_t) + cfg.arrivals.mf_return_delay, kind, round(rate)))
    # Returned unused sets, mostly in the afternoon.
    ulo, uhi = cfg.arrivals.unused_window
    for t in rng.uniform(ulo, uhi, unused):
        sched.append((float(t), "cassette", 1))
    # Emergency and intake patients.
    emergency = int(w.emergency_patients.sample(rng, cfg.scale.units_per_patient))
    for t in rng.uniform(120, 600, emergency):
        for kind, rate in w.per_patient.items():
            n = _poisson(rng, rate)
            if n:
                sched.append((float(t), kind, n))
    return sched, emergency, unused


def backlog_units(estimate: int, cfg: SimConfig) -> list[CarryUnit]:
    """Fresh backlog from the 0-2 scale: a typical mix waiting at decontamination."""
    n = cfg.work.carryover_units.get(int(estimate), 0)
    kinds = ["cassette"] * 6 + ["pouch"] * 3 + ["handpiece"]
    return [CarryUnit(kinds[i % len(kinds)], "decon") for i in range(n)]


def backlog_scale(units: int, cfg: SimConfig) -> int:
    lo, hi = cfg.work.carryover_scale_cuts
    return 0 if units < lo else (1 if units < hi else 2)


def simulate_day(
    inputs: BaseModel,
    cfg: SimConfig,
    rng: np.random.Generator,
    carryover: list[CarryUnit] | None = None,
    diagnostics: bool = False,
) -> DayResult:
    day = complete_inputs(inputs, cfg)
    env = simpy.Environment()
    floor = Floor(env, cfg, rng)
    clock, staff = cfg.clock, cfg.staff

    for unit in (
        carryover if carryover is not None else backlog_units(day.carryover_backlog_estimate, cfg)
    ):
        floor.arrive(unit.kind, unit.stage)

    wid = 0
    stayers = min(day.ot_available_staff, day.morning_staff_present)
    for i in range(day.morning_staff_present):
        stays = i < stayers
        cutoff = clock.ot_cutoff
        if stays:
            cutoff += float(rng.uniform(-clock.cutoff_jitter, clock.cutoff_jitter))
            cutoff = min(cutoff, clock.horizon)
        env.process(worker(env, floor, wid, "morning", 0.0, clock.morning_end, stays, cutoff))
        wid += 1
    for key, count in (
        ("aft_11", day.aft_11_staff),
        ("aft_13", day.aft_13_staff),
        ("aft_15", day.aft_15_staff),
    ):
        start = staff.starts[key]
        end = min(start + staff.shift_length, clock.horizon)
        for _ in range(count):
            env.process(worker(env, floor, wid, key, start, end))
            wid += 1
    for _ in range(day.outside_support_staff):
        env.process(
            worker(
                env, floor, wid, "outside", staff.outside_support_start, staff.outside_support_end
            )
        )
        wid += 1

    dis = cfg.disruptions
    downtime_total = 0.0
    for stage, count in (("wash", day.washers_up), ("sterilize", day.sterilizers_up)):
        for idx in range(count):
            windows: list[tuple[float, float]] = []
            if rng.random() < dis.p_down:
                s = float(rng.uniform(*dis.down_start))
                e = min(s + dis.down_duration.sample(rng), clock.horizon)
                windows.append((s, e))
                downtime_total += e - s
                floor.log.downtime.append((stage, idx, s, e))
            env.process(machine(env, floor, stage, idx, windows))

    schedule, emergency, unused = build_schedule(day, cfg, rng)
    env.process(arrivals(env, floor, schedule))
    if rng.random() < dis.p_bi:
        env.process(bi_recall(env, floor, float(rng.uniform(240, 900))))
    if diagnostics:
        env.process(monitor(env, floor))

    env.run(until=clock.horizon)

    carry = [CarryUnit(u.kind, u.stage) for u in floor.live.values()]
    return DayResult(
        date=day.date,
        inputs=day,
        ot_labor_hours=round(overtime_hours(floor.log.stayer_leaves, clock.morning_end), 2),
        end_backlog_units=len(carry),
        returned_unused_estimate=unused,
        emergency_intake_patients=emergency,
        equipment_downtime_minutes=round(downtime_total),
        last_completion_time=floor.last_completion,
        arrived_units=floor.arrived,
        completed_units=len(floor.completed),
        carryover=carry,
        log=floor.log,
    )


def workdays(start: dt.date, n: int) -> list[dt.date]:
    days: list[dt.date] = []
    d = start
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d += dt.timedelta(days=1)
    return days


def simulate_sequence(
    n_days: int,
    start_date: dt.date,
    cfg: SimConfig,
    seed: int,
    staffing: dict[str, int] | None = None,
) -> list[DayResult]:
    """Consecutive workdays (weekends skipped) with carryover chained from day to day."""
    from sg_sim.sampler import sample_inputs

    rng = np.random.default_rng(seed)
    results: list[DayResult] = []
    carry: list[CarryUnit] | None = None
    for d in workdays(start_date, n_days):
        backlog = backlog_scale(len(carry), cfg) if carry is not None else 1
        inputs = sample_inputs(d, cfg, rng, staffing=staffing, carryover_estimate=backlog)
        result = simulate_day(inputs, cfg, rng, carryover=carry)
        results.append(result)
        carry = result.carryover[: cfg.work.max_carryover_units]
    return results


__all__ = [
    "STAFF_STAGES",
    "DayInputs",
    "DayResult",
    "simulate_day",
    "simulate_sequence",
]
