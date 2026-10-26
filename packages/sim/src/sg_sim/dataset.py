"""Scenario coverage dataset (SG-09): Latin hypercube staffing over 250 x 20-workday sequences,
persisted to Supabase with dataset lineage and to data/sim/<dataset_id>.parquet."""

from __future__ import annotations

import datetime as dt
import json
import os
import uuid
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import qmc

from sg_data.schema import db_columns
from sg_sim.config import SimConfig
from sg_sim.export import content_hash, result_row, to_frame, validate
from sg_sim.run import backlog_scale, simulate_day, workdays

DEMO_DEPARTMENT = "00000000-0000-4000-8000-000000000003"  # supabase/seed.sql
SEQ_DAYS = 20
SEQ_SPACING = dt.timedelta(days=28)
DESIGN_START = dt.date(2007, 1, 1)  # sequences laid end to end so every date is unique


def lhs_staffing(cfg: SimConfig, n: int, seed: int) -> list[dict[str, int]]:
    names = list(cfg.design)
    lo = np.array([cfg.design[k][0] for k in names], dtype=float)
    hi = np.array([cfg.design[k][1] for k in names], dtype=float)
    unit = qmc.LatinHypercube(d=len(names), seed=seed).random(n)
    rows: list[dict[str, int]] = []
    for u in unit:
        vals = lo + u * (hi - lo + 1)  # integer levels lo..hi with equal width
        row = {
            k: int(min(np.floor(v), hi[i]))
            for i, (k, v) in enumerate(zip(names, vals, strict=True))
        }
        rows.append(row)
    # ot_available_staff is designed as a share of morning staff (see configs/dental_cs.yaml).
    share_key = next((k for k in names if k.startswith("ot_available")), None)
    morning_key = next((k for k in names if k.startswith("morning")), None)
    if share_key and morning_key:
        for row, u in zip(rows, unit[:, names.index(share_key)], strict=True):
            row[share_key] = int(np.floor(u * (row[morning_key] + 1)))
            row[share_key] = min(row[share_key], row[morning_key])
    return rows


def _run_sequence(
    args: tuple[SimConfig, dt.date, list[dict[str, int]], int],
) -> list[dict[str, Any]]:
    from sg_sim.sampler import sample_inputs

    cfg, start, staffing, seed = args
    rng = np.random.default_rng(seed)
    carry = None
    out: list[dict[str, Any]] = []
    for d, staff in zip(workdays(start, len(staffing)), staffing, strict=True):
        backlog = backlog_scale(len(carry), cfg) if carry is not None else 1
        inputs = sample_inputs(d, cfg, rng, staffing=staff, carryover_estimate=backlog)
        r = simulate_day(inputs, cfg, rng, carryover=carry)
        out.append(result_row(r))  # rows only: full results are too big to send back
        carry = r.carryover[: cfg.work.max_carryover_units]
    return out


def run_design(
    cfg: SimConfig, days: int, seed: int, workers: int | None = None
) -> list[dict[str, Any]]:
    n_seq = -(-days // SEQ_DAYS)
    staffing = lhs_staffing(cfg, n_seq * SEQ_DAYS, seed)
    seeds = [int(s.generate_state(1)[0]) for s in np.random.SeedSequence(seed).spawn(n_seq)]
    jobs = [
        (cfg, DESIGN_START + k * SEQ_SPACING, staffing[k * SEQ_DAYS : (k + 1) * SEQ_DAYS], seeds[k])
        for k in range(n_seq)
    ]
    if workers == 1:
        chunks = [_run_sequence(j) for j in jobs]
    else:
        # Spawned workers inherit the environment; one BLAS thread each avoids OpenBLAS
        # allocating a large buffer per core in every process.
        for var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
            os.environ.setdefault(var, "1")
        workers = workers or min(8, os.cpu_count() or 1)
        with ProcessPoolExecutor(max_workers=workers) as pool:
            chunks = list(pool.map(_run_sequence, jobs))
    return [r for chunk in chunks for r in chunk][:days]


def build_dataset(
    cfg: SimConfig,
    days: int,
    seed: int,
    department_id: str = DEMO_DEPARTMENT,
    workers: int | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    dataset_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"sg-sim:{cfg.config_hash}:{seed}:{days}"))
    df = validate(to_frame(run_design(cfg, days, seed, workers), department_id, dataset_id))
    meta = {
        "id": dataset_id,
        "department_id": department_id,
        "source": "simulated",
        "name": f"sim-lhs-{days}d-seed{seed}",
        "row_count": len(df),
        "content_hash": content_hash(df),
        "config_hash": cfg.config_hash,
        "seed": seed,
    }
    return df, meta


def write_parquet(df: pd.DataFrame, meta: dict[str, Any], root: Path) -> Path:
    out = root / "data" / "sim" / f"{meta['id']}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    # Sidecar lineage (config hash, seed) so sg ml train knows which config made the rows.
    out.with_suffix(".json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return out


def _plan_rows(df: pd.DataFrame) -> tuple[list[str], list[tuple[Any, ...]]]:
    cols = list(db_columns("shift_plans"))
    src = df.rename(columns={"date": "plan_date"}).copy()
    for c in cols:
        if c.endswith("__missing"):
            src[c] = False
    src["plan_date"] = src["plan_date"].dt.date
    cols = [*cols, "status"]
    src["status"] = "final"
    return cols, [tuple(_py(v) for v in row) for row in src[cols].itertuples(index=False)]


def _actual_rows(df: pd.DataFrame) -> tuple[list[str], list[tuple[Any, ...]]]:
    cols = list(db_columns("shift_actuals"))
    src = df.rename(columns={"date": "shift_date"}).copy()
    src["shift_date"] = src["shift_date"].dt.date
    cols = [*cols, "status"]
    src["status"] = "approved"
    return cols, [tuple(_py(v) for v in row) for row in src[cols].itertuples(index=False)]


def _py(v: Any) -> Any:
    if v is None or (not isinstance(v, str | dt.date) and pd.isna(v)):
        return None
    if isinstance(v, np.generic):
        return v.item()
    return v


def persist(df: pd.DataFrame, meta: dict[str, Any], db_url: str, batch: int = 500) -> None:
    """Write the dataset row, then plans and actuals in batches. The caller (sg sim run) resolves
    db_url through the sg db guards: local or staging only, never prod. A direct postgres
    connection bypasses RLS like the service role. The unique (department, date, source) key
    allows one simulated row per date, so earlier simulated datasets of the department are
    replaced (their rows cascade)."""
    import psycopg

    with psycopg.connect(db_url) as conn, conn.cursor() as cur:
        cur.execute(
            "delete from public.datasets where department_id = %s and source = 'simulated'",
            (meta["department_id"],),
        )
        cur.execute(
            "insert into public.datasets (id, department_id, source, name, row_count, "
            "content_hash, config_hash, seed) values (%(id)s, %(department_id)s, %(source)s, "
            "%(name)s, %(row_count)s, %(content_hash)s, %(config_hash)s, %(seed)s)",
            meta,
        )
        for table, (cols, rows) in (
            ("shift_plans", _plan_rows(df)),
            ("shift_actuals", _actual_rows(df)),
        ):
            sql = (
                f"insert into public.{table} ({', '.join(cols)}) "
                f"values ({', '.join(['%s'] * len(cols))})"
            )
            for i in range(0, len(rows), batch):
                cur.executemany(sql, rows[i : i + batch])
        conn.commit()
