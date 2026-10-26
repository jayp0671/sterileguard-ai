"""python -m sg_ml {train,compare,notebook}. Called by `sg ml ...`."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from sg_ml.data import REPORTS_DIR, ROOT, RUNS_DIR, SIM_DIR

NOTEBOOK_DIR = Path(__file__).resolve().parents[2] / "notebooks"


def _train(args: argparse.Namespace) -> int:
    from sg_ml.data import config_for, load_dataset
    from sg_ml.features import FeatureContext
    from sg_ml.train import save_run, train

    df, meta = load_dataset(args.dataset)
    ctx = FeatureContext.from_config(config_for(meta))
    t0 = time.time()
    result = train(
        df, meta, ctx, args.feature_set, args.seed, tune_trials=args.trials if args.tune else 0
    )
    out = save_run(result, Path(args.runs_dir))
    m = result.run["metrics"]
    print(
        json.dumps(
            {
                "run_id": result.run["run_id"],
                "run_dir": str(out.relative_to(ROOT) if out.is_relative_to(ROOT) else out),
                "seconds": round(time.time() - t0, 1),
                "mae": m["regression"]["hgb_p50"]["mae"],
                "coverage_80": m["regression"]["hgb_p50"]["coverage_80"],
                "vs_best_baseline": m["improvement_vs_best_baseline"],
                "feature_sets": {k: v["mae"] for k, v in m["feature_sets"].items()},
            }
        )
    )
    return 0


def _evaluate(args: argparse.Namespace) -> int:
    """Run the activation gates on a run; write them into metrics.json and the report."""
    import joblib

    from sg_ml import gates
    from sg_ml.data import load_dataset

    run_dir = Path(args.runs_dir) / args.run
    run = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
    artifact = joblib.load(run_dir / "artifact.joblib")
    df, _ = load_dataset(run["dataset_ids"][0], Path(args.sim_dir))
    results = gates.run_gates(run, artifact, df)
    ok = gates.passed(results)
    run["gates"] = [r.to_dict() for r in results]
    run["gates_passed"] = ok
    (run_dir / "metrics.json").write_text(json.dumps(run, indent=2, default=str), encoding="utf-8")
    report = Path(args.reports_dir) / f"{run['run_id']}.md"
    if report.exists():
        text = report.read_text(encoding="utf-8").split("\n## Activation gates")[0]
        verdict = "PASSED" if ok else "FAILED"
        report.write_text(
            f"{text.rstrip()}\n\n## Activation gates: {verdict}\n\n{gates.table(results)}\n",
            encoding="utf-8",
        )
    if args.json:
        summary = {"run_id": run["run_id"], "gates_passed": ok, "gates": run["gates"]}
        print(json.dumps(summary, default=str))
    else:
        print(gates.table(results))
        print(f"\ngates {'passed' if ok else 'FAILED'} for {run['run_id']}")
    return 0 if ok else 1


def _compare(args: argparse.Namespace) -> int:
    from sg_ml.train import load_runs

    rows = []
    for run in load_runs(Path(args.runs_dir)):
        reg = run["metrics"]["regression"]
        rows.append(
            {
                "run_id": run["run_id"],
                "feature_set": run["feature_set"],
                "tuned": run["tuned"],
                "mae": reg["hgb_p50"]["mae"],
                "rmse": reg["hgb_p50"]["rmse"],
                "coverage_80": reg["hgb_p50"]["coverage_80"],
                "best_baseline_mae": min(
                    v["mae"] for k, v in reg.items() if k.startswith("baseline_")
                ),
                "macro_f1": run["metrics"]["classification"]["hgb_classifier"]["macro_f1"],
            }
        )
    if args.json:
        print(json.dumps(rows))
        return 0
    if not rows:
        print("no runs yet: sg ml train")
        return 0
    cols = list(rows[0])
    widths = {c: max(len(c), *(len(str(r[c])) for r in rows)) for c in cols}
    print("  ".join(c.ljust(widths[c]) for c in cols))
    for r in rows:
        print("  ".join(str(r[c]).ljust(widths[c]) for c in cols))
    return 0


def _notebook(args: argparse.Namespace) -> int:
    import nbformat
    from nbclient import NotebookClient

    matches = sorted(NOTEBOOK_DIR.glob(f"{args.run}*.ipynb"))
    if not matches:
        print(f"no notebook {args.run}* in {NOTEBOOK_DIR}", file=sys.stderr)
        return 1
    for path in matches:
        nb = nbformat.read(path, as_version=4)  # type: ignore[no-untyped-call]
        # Notebooks read SG_ML_DATASET / SG_ML_RUN from the environment (CI uses a fixture).
        NotebookClient(
            nb,
            timeout=args.timeout,
            kernel_name="python3",
            resources={"metadata": {"path": str(NOTEBOOK_DIR)}},
        ).execute()
        if args.save:
            nbformat.write(nb, path)  # type: ignore[no-untyped-call]
        print(json.dumps({"notebook": path.name, "cells": len(nb.cells), "ok": True}))
    return 0


def _backend() -> Any:
    """Service-role registry backend. `sg ml` sets these from the sg db guards (never prod)."""
    from sg_ml.registry import PostgresBackend

    missing = [
        v
        for v in ("SG_ML_DB_URL", "SG_ML_SUPABASE_URL", "SG_ML_SERVICE_KEY")
        if not os.environ.get(v)
    ]
    if missing:
        raise SystemExit(
            f"missing {', '.join(missing)}: run through `sg ml ... --env local|staging`"
        )
    return PostgresBackend(
        os.environ["SG_ML_DB_URL"],
        os.environ["SG_ML_SUPABASE_URL"],
        os.environ["SG_ML_SERVICE_KEY"],
        os.environ.get("SG_ML_BUCKET", "models"),
    )


def _register(args: argparse.Namespace) -> int:
    from sg_ml.registry import register

    reg = register(Path(args.runs_dir) / args.run, _backend())
    print(
        json.dumps(
            {"version": reg.version, "artifact_path": reg.artifact_path, **reg.row}, default=str
        )
    )
    return 0


def _activate(args: argparse.Namespace) -> int:
    from sg_ml.registry import RegistryError

    try:
        row = _backend().activate(args.version, os.environ.get("SG_ML_ACTOR") or None)
    except RegistryError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(row, default=str))
    return 0


def _rollback(args: argparse.Namespace) -> int:
    from sg_ml.registry import RegistryError

    try:
        row = _backend().rollback(args.feature_set, os.environ.get("SG_ML_ACTOR") or None)
    except RegistryError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(row, default=str))
    return 0


def _models(args: argparse.Namespace) -> int:
    print(json.dumps(_backend().list(), default=str))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="sg ml")
    sub = p.add_subparsers(dest="cmd", required=True)
    tr = sub.add_parser("train")
    tr.add_argument("--feature-set", choices=["full", "core"], default="full")
    tr.add_argument("--dataset", default=os.environ.get("SG_ML_DATASET", "latest"))
    tr.add_argument("--tune", action="store_true")
    tr.add_argument("--trials", type=int, default=100)
    tr.add_argument("--seed", type=int, default=42)
    tr.add_argument("--runs-dir", default=str(RUNS_DIR))
    cmp_ = sub.add_parser("compare")
    cmp_.add_argument("--runs-dir", default=str(RUNS_DIR))
    cmp_.add_argument("--json", action="store_true")
    nb = sub.add_parser("notebook")
    nb.add_argument("--run", required=True, help="notebook prefix, e.g. 01")
    nb.add_argument("--timeout", type=int, default=1200)
    nb.add_argument("--save", action="store_true", help="write outputs back into the notebook")
    ev = sub.add_parser("evaluate")
    ev.add_argument("--run", required=True)
    ev.add_argument("--runs-dir", default=str(RUNS_DIR))
    ev.add_argument("--sim-dir", default=str(SIM_DIR))
    ev.add_argument("--reports-dir", default=str(REPORTS_DIR))
    ev.add_argument("--json", action="store_true")
    reg = sub.add_parser("register")
    reg.add_argument("--run", required=True)
    reg.add_argument("--runs-dir", default=str(RUNS_DIR))
    act = sub.add_parser("activate")
    act.add_argument("version")
    rb = sub.add_parser("rollback")
    rb.add_argument("--feature-set", choices=["full", "core"], default="full")
    sub.add_parser("models")
    args = p.parse_args(argv)
    handlers = {
        "train": _train,
        "compare": _compare,
        "evaluate": _evaluate,
        "notebook": _notebook,
        "register": _register,
        "activate": _activate,
        "rollback": _rollback,
        "models": _models,
    }
    return handlers[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
