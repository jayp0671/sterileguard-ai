"""python -m sg_ml {train,compare,notebook}. Called by `sg ml ...`."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from sg_ml.data import ROOT, RUNS_DIR

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
    args = p.parse_args(argv)
    return {"train": _train, "compare": _compare, "notebook": _notebook}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
