"""Discrete-event model of one Dental Central Sterile day (SG-09, plan §3, §11).

Clock: minutes from 07:00 (t = 0). Overtime is never a formula: it is the time morning
stayers spend on the floor after 15:00, and they stay only while work in progress is high.

Staff model (the choice the ticket asks to document): every person is a SimPy *process*
rather than a token in a simpy.Resource. A worker exists only between its start and end
times, pulls the highest-priority waiting unit from the staff stage queues, and never starts
a task it cannot finish before it leaves (morning staff who stay are the exception before
15:00). This makes shift changes, the 15:00 stay-or-leave decision and per-person overtime
exact, and it guarantees nobody processes units outside their presence.

Batch machines (washers, sterilizers) are one process per working machine over a shared FIFO
queue. A free machine loads units FIFO up to its capacity in load units (a pouch weighs less
than a cassette), waiting up to max_load_wait minutes for a fuller load. A machine never runs
a cycle that would overlap its downtime window.

Carryover units resume at the stage they reached (a packaged set waits for the sterilizer, it is
not decontaminated again); fresh backlog from the 0-2 scale waits at decontamination.
"""

from __future__ import annotations

import itertools
from collections import deque
from collections.abc import Generator, Iterable
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import simpy

from sg_sim.config import Dist, SimConfig

STAFF_STAGES = ("decon", "inspect", "pack")
MACHINE_STAGES = ("wash", "sterilize")
NEXT_STAGE = {
    "decon": "wash",
    "wash": "inspect",
    "inspect": "pack",
    "pack": "sterilize",
    "sterilize": "done",
}
MACHINE_OF = {"wash": "washer", "sterilize": "sterilizer"}


@dataclass
class Unit:
    uid: int
    kind: str
    stage: str
    weight: float


@dataclass(frozen=True)
class CarryUnit:
    kind: str
    stage: str


@dataclass
class DayLog:
    """Everything tests need to check the model's invariants."""

    # worker -> (role, arrived, left); left stays at the horizon for anyone still on the floor
    presence: dict[int, tuple[str, float, float]] = field(default_factory=dict)
    tasks: list[tuple[int, float, float]] = field(default_factory=list)  # (worker, start, end)
    cycles: list[tuple[str, int, float, float, float]] = field(
        default_factory=list
    )  # (machine kind, index, start, end, load weight)
    downtime: list[tuple[str, int, float, float]] = field(default_factory=list)
    stayer_leaves: list[float] = field(default_factory=list)
    queue_samples: list[dict[str, float]] = field(default_factory=list)


class Floor:
    """Shared state: stage queues, live units and the wake-up signals."""

    def __init__(self, env: simpy.Environment, cfg: SimConfig, rng: np.random.Generator) -> None:
        self.env = env
        self.cfg = cfg
        self.rng = rng
        self.queues: dict[str, deque[Unit]] = {s: deque() for s in (*STAFF_STAGES, *MACHINE_STAGES)}
        self.staff_signal = env.event()
        self.machine_signal = {s: env.event() for s in MACHINE_STAGES}
        self.live: dict[int, Unit] = {}
        self.ids = itertools.count()
        self.arrived = 0
        self.completed: set[int] = set()
        self.present = 0
        self.last_completion = 0.0
        self.loads: list[list[Unit]] = []
        self.log = DayLog()

    # -- signals ----------------------------------------------------------
    def _notify_staff(self) -> None:
        if not self.staff_signal.triggered:
            self.staff_signal.succeed()
        self.staff_signal = self.env.event()

    def _notify_machine(self, stage: str) -> None:
        sig = self.machine_signal[stage]
        if not sig.triggered:
            sig.succeed()
        self.machine_signal[stage] = self.env.event()

    # -- units ------------------------------------------------------------
    def arrive(self, kind: str, stage: str = "decon") -> None:
        unit = Unit(next(self.ids), kind, stage, self.cfg.units[kind].weight)
        self.live[unit.uid] = unit
        self.arrived += 1
        self.enqueue(unit, stage)

    def enqueue(self, unit: Unit, stage: str) -> None:
        unit.stage = stage
        if stage == "done":
            self.completed.add(unit.uid)
            del self.live[unit.uid]
            self.last_completion = max(
                self.last_completion, self.env.now + self.cfg.machines.cool_minutes
            )
            return
        self.queues[stage].append(unit)
        if stage in MACHINE_STAGES:
            self._notify_machine(stage)
        else:
            self._notify_staff()

    def take_staff_task(self) -> tuple[Unit, str] | None:
        for stage in self.cfg.staff.priority:
            if self.queues[stage]:
                return self.queues[stage].popleft(), stage
        return None

    def wip_per_staff(self) -> float:
        return len(self.live) / max(self.present, 1)

    def recall(self, units: Iterable[Unit]) -> None:
        """Biological indicator failure: completed units go back to decontamination."""
        for unit in units:
            if unit.uid in self.completed:
                self.completed.discard(unit.uid)
                self.live[unit.uid] = unit
                self.enqueue(unit, "decon")


def stage_minutes(cfg: SimConfig, kind: str, stage: str, rng: np.random.Generator) -> float:
    dist: Dist = getattr(cfg.units[kind], stage)
    return max(0.05, dist.sample(rng, cfg.scale.stage_time))


def worker(
    env: simpy.Environment,
    floor: Floor,
    wid: int,
    role: str,
    start: float,
    end: float,
    stays: bool = False,
    cutoff: float = 0.0,
) -> Generator[simpy.Event, Any, None]:
    """One person on the floor. Stayers (morning staff willing to do overtime) re-decide after
    15:00 at every task boundary: leave once WIP per staff is low or their cutoff is reached."""
    cfg = floor.cfg
    morning_end = cfg.clock.morning_end
    threshold = cfg.staff.ot_stay_threshold
    if start > env.now:
        yield env.timeout(start - env.now)
    floor.present += 1
    arrived_at = env.now
    floor.log.presence[wid] = (role, arrived_at, cfg.clock.horizon)
    while True:
        now = env.now
        if stays:
            if now >= morning_end and (floor.wip_per_staff() <= threshold or now >= cutoff):
                break
            limit = cutoff
        else:
            if now >= end:
                break
            limit = end
        task = floor.take_staff_task()
        if task is None:
            wait = limit - now
            if stays and now >= morning_end:
                wait = min(wait, 10.0)  # re-check WIP as machines unload
            elif stays:
                wait = min(wait, morning_end - now) or 10.0
            yield env.any_of([floor.staff_signal, env.timeout(max(wait, 0.01))])
            continue
        unit, stage = task
        dur = stage_minutes(cfg, unit.kind, stage, floor.rng)
        if now + dur > limit:
            floor.queues[stage].appendleft(unit)  # cannot finish before leaving
            yield env.timeout(limit - now)
            continue
        yield env.timeout(dur)
        floor.log.tasks.append((wid, now, env.now))
        floor.enqueue(unit, NEXT_STAGE[stage])
    floor.present -= 1
    floor.log.presence[wid] = (role, arrived_at, env.now)
    if stays:
        floor.log.stayer_leaves.append(env.now)


def _take_load(queue: deque[Unit], capacity: float) -> list[Unit]:
    batch: list[Unit] = []
    total = 0.0
    while queue and (not batch or total + queue[0].weight <= capacity):
        unit = queue.popleft()
        batch.append(unit)
        total += unit.weight
    return batch


def _queued_weight(queue: deque[Unit]) -> float:
    return sum(u.weight for u in queue)


def machine(
    env: simpy.Environment,
    floor: Floor,
    stage: str,
    index: int,
    windows: list[tuple[float, float]],
) -> Generator[simpy.Event, Any, None]:
    kind = MACHINE_OF[stage]
    mcfg = getattr(floor.cfg.machines, kind)
    queue = floor.queues[stage]
    while True:
        if not queue:
            yield floor.machine_signal[stage]
            continue
        if _queued_weight(queue) < mcfg.capacity:
            deadline = env.now + mcfg.max_load_wait
            while queue and _queued_weight(queue) < mcfg.capacity and env.now < deadline:
                yield env.any_of([floor.machine_signal[stage], env.timeout(deadline - env.now)])
            if not queue:
                continue
        cycle = mcfg.cycle.sample(floor.rng)
        blocked = [(s, e) for s, e in windows if env.now < e and env.now + cycle > s]
        if blocked:
            yield env.timeout(max(e for _, e in blocked) - env.now)
            continue
        batch = _take_load(queue, mcfg.capacity)
        start = env.now
        yield env.timeout(cycle)
        floor.log.cycles.append((kind, index, start, env.now, sum(u.weight for u in batch)))
        if stage == "sterilize":
            floor.loads.append(batch)
        for unit in batch:
            floor.enqueue(unit, NEXT_STAGE[stage])


def arrivals(
    env: simpy.Environment, floor: Floor, schedule: list[tuple[float, str, int]]
) -> Generator[simpy.Event, Any, None]:
    for t, kind, count in sorted(schedule, key=lambda x: (x[0], x[1])):
        if t > env.now:
            yield env.timeout(t - env.now)
        for _ in range(count):
            floor.arrive(kind)


def monitor(env: simpy.Environment, floor: Floor) -> Generator[simpy.Event, Any, None]:
    while True:
        sample: dict[str, float] = {"t": env.now, "staff": floor.present}
        sample.update({s: len(q) for s, q in floor.queues.items()})
        floor.log.queue_samples.append(sample)
        yield env.timeout(15)


def bi_recall(env: simpy.Environment, floor: Floor, at: float) -> Generator[simpy.Event, Any, None]:
    yield env.timeout(at)
    for load in floor.loads[-floor.cfg.disruptions.bi_loads :]:
        floor.recall(load)
