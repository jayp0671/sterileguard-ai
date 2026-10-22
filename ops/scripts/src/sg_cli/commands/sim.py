"""sg sim: the SimPy simulator (SG-09). Thin wrapper over `python -m sg_sim` so sg-cli stays
light. The database URL goes through the sg db guards and is never prod."""

from __future__ import annotations

from pathlib import Path

import typer

from sg_cli import core
from sg_cli.commands.db import db_url

app = typer.Typer(no_args_is_help=True)


def _env_url(env: str) -> dict[str, str]:
    if env == "none":
        return {}
    if env not in ("local", "staging"):
        raise typer.BadParameter("--env must be local, staging or none (never prod)")
    return {"SG_SIM_DB_URL": db_url(env)}


@app.command("run", help="Scenario coverage dataset (LHS), saved to parquet and Supabase.")
def run(
    design: str = typer.Option("lhs", "--design"),
    days: int = typer.Option(5000, "--days"),
    seed: int = typer.Option(42, "--seed"),
    env: str = typer.Option("local", "--env", help="local | staging | none"),
    workers: int = typer.Option(0, "--workers", help="0 = up to 8 processes"),
) -> None:
    result = core.Result("sim", "run")
    cmd = [
        "uv",
        "run",
        "python",
        "-m",
        "sg_sim",
        "run",
        "--design",
        design,
        "--days",
        str(days),
        "--seed",
        str(seed),
    ]
    if workers:
        cmd += ["--workers", str(workers)]
    if env == "none":
        cmd.append("--no-upload")
    core.run(cmd, env=_env_url(env))
    result.data.update(design=design, days=days, seed=seed, env=env)
    result.add(f"simulated {days} days (seed {seed}), upload target: {env}")
    result.finish()


@app.command("calibrate", help="Optuna calibration against real days; writes the report.")
def calibrate(
    real_csv: Path | None = typer.Option(None, "--real-csv", help="Private CSV, never committed."),
    trials: int = typer.Option(200, "--trials"),
    reps: int = typer.Option(30, "--reps"),
    seed: int = typer.Option(42, "--seed"),
    env: str = typer.Option("none", "--env", help="read real rows from local | staging | none"),
) -> None:
    result = core.Result("sim", "calibrate")
    cmd = [
        "uv",
        "run",
        "python",
        "-m",
        "sg_sim",
        "calibrate",
        "--trials",
        str(trials),
        "--reps",
        str(reps),
        "--seed",
        str(seed),
    ]
    if real_csv:
        cmd += ["--real-csv", str(real_csv)]
    core.run(cmd, env=_env_url(env))
    result.add("calibration written to packages/sim/configs/dental_cs.calibrated.yaml")
    result.finish()


@app.command("validate", help="KS tests of simulated vs real distributions (5+ real days).")
def validate(
    real_csv: Path | None = typer.Option(None, "--real-csv"),
    env: str = typer.Option("none", "--env"),
) -> None:
    result = core.Result("sim", "validate")
    cmd = ["uv", "run", "python", "-m", "sg_sim", "validate"]
    if real_csv:
        cmd += ["--real-csv", str(real_csv)]
    core.run(cmd, env=_env_url(env))
    result.add("validation report written to ops/reports/sim/validation.md")
    result.finish()
