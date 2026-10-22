"""SimConfig: the YAML config as typed Pydantic models, plus distribution sampling."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

import numpy as np
import yaml
from pydantic import BaseModel, ConfigDict

CONFIG_DIR = Path(__file__).resolve().parents[2] / "configs"
DEFAULT_CONFIG = CONFIG_DIR / "dental_cs.yaml"


class Dist(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dist: Literal["triangular", "lognormal", "poisson", "normal_trunc", "const"]
    low: float = 0.0
    mode: float = 0.0
    high: float = 0.0
    median: float = 0.0
    sigma: float = 0.0
    lam: float = 0.0
    mean: float = 0.0
    sd: float = 0.0
    value: float = 0.0

    def sample(self, rng: np.random.Generator, scale: float = 1.0) -> float:
        if self.dist == "const":
            return self.value * scale
        if self.dist == "triangular":
            if self.low == self.high:
                return self.low * scale
            return float(rng.triangular(self.low, self.mode, self.high)) * scale
        if self.dist == "lognormal":
            x = float(rng.lognormal(np.log(self.median), self.sigma))
            return float(np.clip(x, self.low or 0.0, self.high or np.inf)) * scale
        if self.dist == "poisson":
            return float(rng.poisson(self.lam * scale))
        x = float(rng.normal(self.mean, self.sd))
        return float(np.clip(x, self.low, self.high)) * scale


class Clock(BaseModel):
    horizon: float
    ot_cutoff: float
    cutoff_jitter: float
    morning_end: float


class Staff(BaseModel):
    shift_length: float
    starts: dict[str, float]
    outside_support_start: float
    outside_support_end: float
    ot_stay_threshold: float
    priority: list[Literal["decon", "inspect", "pack"]]


class UnitType(BaseModel):
    weight: float
    decon: Dist
    inspect: Dist
    pack: Dist


class Work(BaseModel):
    per_patient: dict[str, float]
    per_mf_case: dict[str, float]
    per_session: dict[str, float]
    unused_share: float
    unused_factor: Dist
    emergency_patients: Dist
    carryover_units: dict[int, int]
    carryover_scale_cuts: list[int]
    max_carryover_units: int = 400


class Block(BaseModel):
    first_pickup: float
    last_pickup: float
    share: float


class Arrivals(BaseModel):
    blocks: list[Block]
    pickup_interval: Dist
    mf_case_window: tuple[float, float]
    mf_return_delay: float
    unused_window: tuple[float, float]


class Machine(BaseModel):
    capacity: float
    cycle: Dist
    max_load_wait: float


class Machines(BaseModel):
    washer: Machine
    sterilizer: Machine
    cool_minutes: float


class Disruptions(BaseModel):
    p_down: float
    down_start: tuple[float, float]
    down_duration: Dist
    p_bi: float
    bi_loads: int


class Scale(BaseModel):
    units_per_patient: float = 1.0
    units_per_session: float = 1.0
    stage_time: float = 1.0


class Event(BaseModel):
    name: Literal["exam", "break", "semester_start"]
    start: str
    end: str
    patient_factor: float = 1.0
    session_factor: float = 1.0


class Calendar(BaseModel):
    patients_mean: float
    patients_sd: float
    weekday_multipliers: list[float]
    mf_lambda: float
    sessions_mean: float
    holiday_dates: list[str] = []
    events: list[Event] = []


class SimConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    clock: Clock
    department_settings: dict[str, Any]
    staff: Staff
    units: dict[str, UnitType]
    work: Work
    arrivals: Arrivals
    machines: Machines
    disruptions: Disruptions
    scale: Scale
    calendar: Calendar
    design: dict[str, tuple[float, float]] = {}

    @property
    def config_hash(self) -> str:
        """sha256 of the canonical (sorted-keys) config."""
        canon = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canon.encode()).hexdigest()


def load_config(path: Path | str | None = None) -> SimConfig:
    raw = yaml.safe_load(Path(path or DEFAULT_CONFIG).read_text(encoding="utf-8"))
    return SimConfig.model_validate(raw)
