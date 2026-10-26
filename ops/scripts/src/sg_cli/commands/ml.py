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


# Registry (SG-14). Service-role credentials come from .env through the sg db guards; prod is
# refused here: production activation goes through the API with re-authentication.
_ENV_VARS = {
    "local": ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"),
    "staging": ("SUPABASE_URL_STAGING", "SUPABASE_SERVICE_ROLE_KEY_STAGING"),
}


def _registry_env(env: str) -> dict[str, str]:
    from sg_cli.commands.db import db_url

    if env not in _ENV_VARS:
        raise typer.BadParameter("--env must be local or staging (never prod)")
    url_var, key_var = _ENV_VARS[env]
    found = core.require_env(url_var, key_var)
    return {
        "SG_ML_DB_URL": db_url(env),
        "SG_ML_SUPABASE_URL": found[url_var],
        "SG_ML_SERVICE_KEY": found[key_var],
        "SG_ML_BUCKET": core.env_value("MODEL_BUCKET") or "models",
    }


@app.command("register", help="Upload a run's artifact and card; insert a candidate version.")
def register(
    run: str = typer.Option(..., "--run", help="run id under data/runs/"),
    env: str = typer.Option("local", "--env", help="local | staging"),
) -> None:
    result = core.Result("ml", "register")
    core.run(_ml("register", "--run", run), env=_registry_env(env))
    result.data.update(run=run, env=env)
    result.add(f"registered {run} on {env} as a candidate")
    result.finish()


@app.command("activate", help="Activate a version (refused unless its gates passed).")
def activate(
    version: str = typer.Argument(...),
    env: str = typer.Option("local", "--env", help="local | staging"),
) -> None:
    result = core.Result("ml", "activate")
    core.run(_ml("activate", version), env=_registry_env(env))
    result.add(f"activated {version} on {env}")
    result.finish()


@app.command("rollback", help="Re-activate the most recent retired version.")
def rollback(
    feature_set: str = typer.Option("full", "--feature-set", help="full | core"),
    env: str = typer.Option("local", "--env", help="local | staging"),
) -> None:
    result = core.Result("ml", "rollback")
    core.run(_ml("rollback", "--feature-set", feature_set), env=_registry_env(env))
    result.add(f"rolled back {feature_set} on {env}")
    result.finish()


@app.command("models", help="List registered versions.")
def models(env: str = typer.Option("local", "--env", help="local | staging")) -> None:
    result = core.Result("ml", "models")
    core.run(_ml("models"), env=_registry_env(env))
    result.finish()
