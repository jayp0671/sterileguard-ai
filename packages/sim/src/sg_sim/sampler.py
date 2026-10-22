"""Calendar-aware demand sampler (SG-09): weekday effect from the week-1 pattern, MF cases
~ Poisson(20), student sessions from the academic calendar config."""

from __future__ import annotations

import datetime as dt
from typing import Any

import numpy as np

from sg_sim.config import SimConfig
from sg_sim.run import DayInputs, complete_inputs


def academic_event(d: dt.date, cfg: SimConfig) -> tuple[str, float, float]:
    for ev in cfg.calendar.events:
        if dt.date.fromisoformat(ev.start) <= d <= dt.date.fromisoformat(ev.end):
            return ev.name, ev.patient_factor, ev.session_factor
    return "none", 1.0, 1.0


def sample_demand(d: dt.date, cfg: SimConfig, rng: np.random.Generator) -> dict[str, Any]:
    cal = cfg.calendar
    holiday = d.isoformat() in cal.holiday_dates
    event, pf, sf = academic_event(d, cfg)
    mult = cal.weekday_multipliers[d.weekday()] if d.weekday() < 5 else 0.3
    if holiday:
        pf, sf = 0.05, 0.0
    mean = cal.patients_mean * mult * pf
    patients = int(np.clip(round(rng.normal(mean, cal.patients_sd * max(pf, 0.2))), 0, 800))
    return dict(
        date=d,
        regular_patients=patients,
        mf_cases=int(min(rng.poisson(cal.mf_lambda * (0.1 if holiday else 1.0)), 80)),
        student_clinic_sessions=int(min(rng.poisson(cal.sessions_mean * sf), 40)),
        is_holiday=holiday,
        academic_event=event,
    )


def sample_inputs(
    d: dt.date,
    cfg: SimConfig,
    rng: np.random.Generator,
    staffing: dict[str, int] | None = None,
    carryover_estimate: int = 1,
) -> DayInputs:
    """Demand from the calendar; staffing and equipment from `staffing` or department defaults
    (morning staff default 3, plan §3)."""
    values = sample_demand(d, cfg, rng)
    values.update(morning_staff_present=3, carryover_backlog_estimate=carryover_estimate)
    values.update(staffing or {})
    return complete_inputs(DayInputs(**values), cfg)
