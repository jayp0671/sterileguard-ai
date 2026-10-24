"""python -m sg_sim {run,calibrate,validate}. Called by `sg sim ...`, which resolves the
database URL through the sg db guards and passes it in SG_SIM_DB_URL (never prod)."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from sg_sim.config import CONFIG_DIR, load_config

ROOT = Path(__file__).resolve().parents[4]
REPORTS = ROOT / "ops" / "reports" / "sim"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="sg sim")
    sub = p.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run")
    run.add_argument("--design", choices=["lhs"], default="lhs")
    run.add_argument("--days", type=int, default=5000)
    run.add_argument("--seed", type=int, default=42)
    run.add_argument("--config", type=Path)
    run.add_argument("--workers", type=int)
    run.add_argument("--no-upload", action="store_true")
    cal = sub.add_parser("calibrate")
    cal.add_argument("--real-csv", type=Path)
    cal.add_argument("--trials", type=int, default=200)
    cal.add_argument("--reps", type=int, default=30)
    cal.add_argument("--seed", type=int, default=42)
    val = sub.add_parser("validate")
    val.add_argument("--real-csv", type=Path)
    val.add_argument("--days", type=int, default=500)
    val.add_argument("--seed", type=int, default=42)
    args = p.parse_args(argv)
    db_url = os.environ.get("SG_SIM_DB_URL") or None

    if args.cmd == "run":
        from sg_sim.dataset import build_dataset, persist, write_parquet

        cfg = load_config(args.config)
        t0 = time.time()
        df, meta = build_dataset(cfg, args.days, args.seed, workers=args.workers)
        parquet = write_parquet(df, meta, ROOT)
        uploaded = False
        if db_url and not args.no_upload:
            persist(df, meta, db_url)
            uploaded = True
        summary = {
            **meta,
            "seconds": round(time.time() - t0, 1),
            "parquet": str(parquet.relative_to(ROOT)),
            "uploaded": uploaded,
            "ot_mean": round(float(df["ot_labor_hours"].mean()), 2),
            "ot_zero_share": round(float((df["ot_labor_hours"] == 0).mean()), 3),
        }
        print(json.dumps(summary))
        return 0

    from sg_sim.calibrate import (
        calibrate,
        ks_validate,
        load_real,
        real_inputs,
        write_calibrated,
        write_report,
    )

    cfg = load_config()
    real_df = load_real(args.real_csv, db_url, cfg.department_settings)
    if args.cmd == "calibrate":
        real = real_inputs(real_df) if not real_df.empty else []
        best, ev = calibrate(cfg, real, trials=args.trials, reps=args.reps, seed=args.seed)
        write_calibrated(cfg, best, CONFIG_DIR / "dental_cs.calibrated.yaml")
        report = write_report(ev, best, len(real), REPORTS)
        print(
            json.dumps(
                {
                    "real_days": len(real),
                    "loss": round(ev.loss, 3),
                    "mae": ev.mae,
                    "best": best,
                    "report": str(report.relative_to(ROOT)),
                }
            )
        )
        return 0

    from sg_sim.dataset import build_dataset

    sim_df, _ = build_dataset(cfg, args.days, args.seed)
    report = ks_validate(sim_df, real_df, REPORTS)
    print(json.dumps({"real_days": len(real_df), "report": str(report.relative_to(ROOT))}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
