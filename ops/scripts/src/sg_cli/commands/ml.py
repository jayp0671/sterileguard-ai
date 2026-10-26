"""sg ml: training, comparison and notebooks (SG-13). Thin wrapper over `python -m sg_ml` so
sg-cli stays light."""

from __future__ import annotations

import typer

from sg_cli import core

app = typer.Typer(no_args_is_help=True)


def _ml(*args: str) -> list[str]:
    return ["uv", "run", "python", "-m", "sg_ml", *args]


@app.command("train", help="Train baselines and models; saves data/runs/<run_id>/.")
def train(
    feature_set: str = typer.Option("full", "--feature-set", help="full | core"),
    dataset: str = typer.Option("latest", "--dataset", help="dataset id, latest, or a .parquet"),
    tune: bool = typer.Option(False, "--tune", help="Optuna TPE, 100 trials"),
    trials: int = typer.Option(100, "--trials"),
    seed: int = typer.Option(42, "--seed"),
) -> None:
    if feature_set not in ("full", "core"):
        raise typer.BadParameter("--feature-set must be full or core")
    result = core.Result("ml", "train")
    cmd = _ml("train", "--feature-set", feature_set, "--dataset", dataset, "--seed", str(seed))
    if tune:
        cmd += ["--tune", "--trials", str(trials)]
    core.run(cmd)
    result.data.update(feature_set=feature_set, dataset=dataset, tune=tune, seed=seed)
    result.add(f"trained {feature_set} on {dataset}; report in ops/reports/models/")
    result.finish()


@app.command("compare", help="Table of metrics across runs.")
def compare() -> None:
    result = core.Result("ml", "compare")
    core.run(_ml("compare"))
    result.finish()


@app.command("notebook", help="Execute a notebook top to bottom (nbclient).")
def notebook(
    run: str = typer.Option(..., "--run", help="notebook prefix, e.g. 01"),
    save: bool = typer.Option(False, "--save", help="keep outputs in the notebook"),
) -> None:
    result = core.Result("ml", "notebook")
    core.run(_ml("notebook", "--run", run, *(["--save"] if save else [])))
    result.add(f"notebook {run} executed")
    result.finish()
