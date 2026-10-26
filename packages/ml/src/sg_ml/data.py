"""Dataset and run locations (SG-13). Simulated datasets are parquet files written by
`sg sim run` to data/sim/<id>.parquet with a <id>.json lineage sidecar; runs go to
data/runs/<run_id>/. Both folders are gitignored."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from sg_sim.config import CONFIG_DIR, SimConfig, load_config

ROOT = Path(__file__).resolve().parents[4]
SIM_DIR = ROOT / "data" / "sim"
RUNS_DIR = ROOT / "data" / "runs"
REPORTS_DIR = ROOT / "ops" / "reports" / "models"
CALIBRATED = CONFIG_DIR / "dental_cs.calibrated.yaml"


def resolve_dataset(ref: str, sim_dir: Path = SIM_DIR) -> Path:
    """'latest' (newest parquet), a dataset id, or a path to a parquet file."""
    if ref == "latest":
        files = sorted(sim_dir.glob("*.parquet"), key=lambda p: p.stat().st_mtime)
        if not files:
            raise FileNotFoundError(f"no datasets in {sim_dir}; run `sg sim run` first")
        return files[-1]
    path = Path(ref)
    if path.suffix == ".parquet":
        return path
    candidate = sim_dir / f"{ref}.parquet"
    if not candidate.exists():
        raise FileNotFoundError(f"dataset {ref} not found in {sim_dir}")
    return candidate


def load_dataset(ref: str, sim_dir: Path = SIM_DIR) -> tuple[pd.DataFrame, dict[str, Any]]:
    path = resolve_dataset(ref, sim_dir)
    df = pd.read_parquet(path)
    sidecar = path.with_suffix(".json")
    meta: dict[str, Any] = (
        json.loads(sidecar.read_text(encoding="utf-8")) if sidecar.exists() else {}
    )
    meta.setdefault("id", path.stem)
    return df, meta


def config_for(meta: dict[str, Any]) -> SimConfig:
    """The simulator config whose hash produced the dataset, else the calibrated config."""
    wanted = meta.get("config_hash")
    if wanted:
        for path in sorted(CONFIG_DIR.glob("*.yaml")):
            cfg = load_config(path)
            if cfg.config_hash == wanted:
                return cfg
    return load_config(CALIBRATED)
