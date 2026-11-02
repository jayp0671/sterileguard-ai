"""Column profile of a parsed file (SG-21, plan §10.1 step 3). Columns flagged by the PHI guard
never get sample values recorded."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pandas as pd

SAMPLES = 5


def _dtype(values: pd.Series) -> str:
    if values.empty:
        return "empty"
    if pd.to_numeric(values.astype(str).str.replace(",", ""), errors="coerce").notna().all():
        return "number"
    if values.map(lambda v: hasattr(v, "year")).all():
        return "date"
    if pd.to_datetime(values.astype(str), errors="coerce", format="mixed").notna().all():
        return "date"
    return "text"


def profile(df: pd.DataFrame, phi_columns: Iterable[str] = ()) -> list[dict[str, Any]]:
    flagged = set(phi_columns)
    out: list[dict[str, Any]] = []
    for col in df.columns:
        s = df[col]
        present = s.dropna()
        kind = _dtype(present)
        entry: dict[str, Any] = {
            "column": str(col),
            "dtype": kind,
            "null_pct": round(100 * (1 - len(present) / len(s)), 1) if len(s) else 0.0,
            "distinct": int(present.astype(str).nunique()),
            "min": None,
            "max": None,
            "samples": [],
            "phi": str(col) in flagged,
        }
        if kind == "number" and len(present):
            nums = pd.to_numeric(present.astype(str).str.replace(",", ""))
            entry["min"], entry["max"] = float(nums.min()), float(nums.max())
        elif kind == "date" and len(present):
            dates = pd.to_datetime(present.astype(str), errors="coerce", format="mixed")
            entry["min"], entry["max"] = str(dates.min().date()), str(dates.max().date())
        if not entry["phi"]:
            entry["samples"] = [str(v) for v in present.astype(str).unique()[:SAMPLES]]
        out.append(entry)
    return out
