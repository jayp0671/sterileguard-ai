"""Calibration (sg sim calibrate) and validation (sg sim validate), SG-09.

Primary target: each real day's actual Tier 1 inputs (Tier 2 from defaults where missing) are
simulated `reps` times; loss = MAE between the median simulated ot_labor_hours and the real
value. Plausibility penalties: mean stayer leave time outside 20:00-21:00, the share of days
with overtime differing from real, and carryover drifting upward across a 20-day sequence.
With no real days yet, only the penalties are used and the report says so.

Real data is read from a private CSV (--real-csv) or from Supabase rows with source = 'real'.
It is never written to the repo; reports hold aggregates and plots only.
"""

from __future__ import annotations

import datetime as dt
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from sg_data.defaults import fill_tier2
from sg_data.schema import INPUT_FIELDS, to_pandera
from sg_sim.config import SimConfig
from sg_sim.run import DayInputs, DayResult, simulate_day, simulate_sequence

# Bounded free parameters: (dotted path in the config, low, high).
FREE_PARAMS: dict[str, tuple[str, float, float]] = {
    "units_per_patient": ("scale.units_per_patient", 0.6, 1.6),
    "units_per_session": ("scale.units_per_session", 0.5, 1.5),
    "stage_time": ("scale.stage_time", 0.35, 1.0),
    "ot_stay_threshold": ("staff.ot_stay_threshold", 5.0, 60.0),
    "p_down": ("disruptions.p_down", 0.0, 0.05),
    "unused_share": ("work.unused_share", 0.1, 0.4),
}
LEAVE_WINDOW = (13 * 60.0, 14 * 60.0)  # 20:00 to 21:00 in minutes from 07:00


def with_params(cfg: SimConfig, params: dict[str, float]) -> SimConfig:
    data = cfg.model_dump()
    for name, value in params.items():
        node = data
        *head, leaf = FREE_PARAMS[name][0].split(".")
        for part in head:
            node = node[part]
        node[leaf] = value
    return SimConfig.model_validate(data)


def load_real(real_csv: Path | None, db_url: str | None, settings: dict[str, Any]) -> pd.DataFrame:
    if real_csv is not None:
        df = pd.read_csv(real_csv)
    elif db_url:
        import psycopg

        sql = (
            "select p.*, a.ot_labor_hours from public.shift_plans p join public.shift_actuals a "
            "on a.department_id = p.department_id and a.shift_date = p.plan_date "
            "and a.source = p.source where p.source = 'real'"
        )
        with psycopg.connect(db_url) as conn:
            cur = conn.execute(sql)
            cols = [c.name for c in cur.description or []]
            df = pd.DataFrame(cur.fetchall(), columns=cols).rename(columns={"plan_date": "date"})
    else:
        return pd.DataFrame()
    if df.empty:
        return df
    df = fill_tier2(df, settings)
    to_pandera({"input", "outcome"}).validate(df, lazy=True)
    return df


def real_inputs(df: pd.DataFrame) -> list[tuple[DayInputs, float]]:
    out = []
    for _, row in df.iterrows():
        values = {k: row[k] for k in INPUT_FIELDS if k in row and not pd.isna(row[k])}
        values["date"] = pd.Timestamp(values["date"]).date()
        out.append((DayInputs(**values), float(row["ot_labor_hours"])))
    return out


@dataclass
class Evaluation:
    loss: float
    mae: float | None
    mean_leave: float
    ot_share: float
    drift: float
    per_day: list[tuple[str, float, float]]
    sequence: list[DayResult]


def evaluate(
    cfg: SimConfig, real: list[tuple[DayInputs, float]], reps: int, seed: int
) -> Evaluation:
    rng = np.random.default_rng(seed)
    per_day: list[tuple[str, float, float]] = []
    leaves: list[float] = []
    for inputs, actual in real:
        sims = [simulate_day(inputs, cfg, rng) for _ in range(reps)]
        leaves += [t for s in sims for t in s.log.stayer_leaves]
        per_day.append(
            (inputs.date.isoformat(), actual, statistics.median(s.ot_labor_hours for s in sims))
        )
    seq = simulate_sequence(20, dt.date(2026, 9, 7), cfg, seed)
    leaves += [t for s in seq for t in s.log.stayer_leaves]
    backlog = [s.end_backlog_units for s in seq]
    drift = float(np.polyfit(np.arange(len(backlog)), backlog, 1)[0])
    mean_leave = float(np.mean(leaves)) if leaves else LEAVE_WINDOW[0]
    sim_share = float(np.mean([s.ot_labor_hours > 0 for s in seq]))
    real_share = float(np.mean([a > 0 for _, a in real])) if real else 0.9
    mae = float(np.mean([abs(a - m) for _, a, m in per_day])) if per_day else None
    lo, hi = LEAVE_WINDOW
    leave_pen = max(0.0, lo - mean_leave, mean_leave - hi) / 30.0
    loss = (mae or 0.0) + leave_pen + 2.0 * abs(sim_share - real_share) + max(0.0, drift) / 10.0
    return Evaluation(loss, mae, mean_leave, sim_share, drift, per_day, seq)


def calibrate(
    cfg: SimConfig,
    real: list[tuple[DayInputs, float]],
    trials: int = 200,
    reps: int = 30,
    seed: int = 42,
) -> tuple[dict[str, float], Evaluation]:
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)

    def objective(trial: optuna.Trial) -> float:
        params = {k: trial.suggest_float(k, lo, hi) for k, (_, lo, hi) in FREE_PARAMS.items()}
        return evaluate(with_params(cfg, params), real, reps, seed).loss

    study = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler(seed=seed))
    study.enqueue_trial({k: _get(cfg, path) for k, (path, _, _) in FREE_PARAMS.items()})
    study.optimize(objective, n_trials=trials)
    best = {k: float(v) for k, v in study.best_params.items()}
    return best, evaluate(with_params(cfg, best), real, reps, seed)


def _get(cfg: SimConfig, path: str) -> float:
    node: Any = cfg.model_dump()
    for part in path.split("."):
        node = node[part]
    return float(node)


def write_calibrated(cfg: SimConfig, best: dict[str, float], out: Path) -> None:
    data = with_params(cfg, best).model_dump(mode="json")
    header = (
        "# GENERATED by `sg sim calibrate` from dental_cs.yaml. Do not edit by hand.\n"
        f"# Calibrated parameters: {', '.join(f'{k}={v:.4g}' for k, v in best.items())}\n"
    )
    out.write_text(header + yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def write_report(ev: Evaluation, best: dict[str, float], n_real: int, out_dir: Path) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 3, figsize=(15, 4))
    if ev.per_day:
        x = np.arange(len(ev.per_day))
        axes[0].bar(x - 0.2, [a for _, a, _ in ev.per_day], 0.4, label="real")
        axes[0].bar(x + 0.2, [m for _, _, m in ev.per_day], 0.4, label="simulated median")
        axes[0].legend()
    else:
        axes[0].text(0.5, 0.5, "no real days yet", ha="center")
    axes[0].set_title("Overtime per real day (hours)")
    leaves = [t / 60 + 7 for s in ev.sequence for t in s.log.stayer_leaves]
    axes[1].hist(leaves, bins=20)
    axes[1].set_title("Stayer leave time (hour of day)")
    axes[2].plot([s.end_backlog_units for s in ev.sequence], marker="o")
    axes[2].set_title("End-of-day backlog over 20 workdays (units)")
    fig.tight_layout()
    fig.savefig(out_dir / "calibration.png", dpi=110)
    plt.close(fig)
    lines = [
        "# Simulator calibration report",
        "",
        f"Real days used: {n_real}."
        + (" No real days yet: plausibility-only calibration." if n_real == 0 else ""),
        "",
        f"- Loss: {ev.loss:.3f}",
        f"- MAE vs real overtime: {'n/a' if ev.mae is None else f'{ev.mae:.2f} h'}",
        f"- Mean stayer leave time: {ev.mean_leave / 60 + 7:.2f} h (target 20 to 21)",
        f"- Share of days with overtime: {ev.ot_share:.2f}",
        f"- Backlog drift: {ev.drift:+.1f} units/day over 20 workdays",
        "",
        "## Calibrated parameters",
        "",
        *[f"- {k}: {v:.4g}" for k, v in best.items()],
        "",
        "![calibration](calibration.png)",
        "",
    ]
    path = out_dir / "calibration.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def ks_validate(sim: pd.DataFrame, real: pd.DataFrame, out_dir: Path) -> Path:
    """Kolmogorov-Smirnov tests of simulated vs real distributions (needs 5+ real days)."""
    from scipy.stats import ks_2samp

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "validation.md"
    if len(real) < 5:
        path.write_text(
            f"# Simulator validation\n\nOnly {len(real)} real days; KS tests need at least 5.\n",
            encoding="utf-8",
        )
        return path
    lines = [
        "# Simulator validation",
        "",
        "| Field | KS statistic | p-value |",
        "| --- | --- | --- |",
    ]
    for col in ("ot_labor_hours", "regular_patients", "equipment_downtime_minutes"):
        if col in real and col in sim:
            r = ks_2samp(sim[col].dropna(), real[col].dropna())
            lines.append(f"| {col} | {r.statistic:.3f} | {r.pvalue:.3f} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
