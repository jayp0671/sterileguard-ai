"""Turn simulated days into rows that validate against the sg_data schema (SG-09)."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from typing import Any

import pandas as pd

from sg_data.schema import FIELDS, to_pandera
from sg_sim.run import DayResult

COLUMNS = [f.name for f in FIELDS]


def result_row(r: DayResult) -> dict[str, Any]:
    """Inputs plus outcomes of one day: small enough to send back from worker processes."""
    row: dict[str, Any] = r.inputs.model_dump()
    row.update(r.outcomes())
    return row


def to_frame(
    results: Iterable[DayResult | dict[str, Any]],
    department_id: str,
    dataset_id: str | None = None,
) -> pd.DataFrame:
    rows = []
    for r in results:
        row = dict(r) if isinstance(r, dict) else result_row(r)
        row.update(
            department_id=department_id,
            source="simulated",
            dataset_id=dataset_id,
            created_by=None,
            notes=None,
        )
        rows.append(row)
    df = pd.DataFrame(rows, columns=COLUMNS)
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date", kind="stable").reset_index(drop=True)


def validate(df: pd.DataFrame) -> pd.DataFrame:
    """Every exported row must pass the canonical schema before upload."""
    return to_pandera().validate(df, lazy=True)


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    out = df.copy()
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    return out.to_csv(index=False, lineterminator="\n", float_format="%.2f").encode()


def content_hash(df: pd.DataFrame) -> str:
    return hashlib.sha256(to_csv_bytes(df)).hexdigest()
