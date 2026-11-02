"""Validate canonical rows with the pandera schema from sg_data (SG-21, plan §10.1 step 7).
Errors are row-level and point at the row of the user's file: {row, column, value, message}."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd
import pandera.errors as pa_errors

from sg_data.imports.transform import DATE
from sg_data.schema import Role, fields, to_pandera


@dataclass
class ValidationResult:
    valid: pd.DataFrame
    errors: list[dict[str, Any]] = field(default_factory=list)

    @property
    def error_rows(self) -> list[int]:
        return sorted({int(e["row"]) for e in self.errors if e.get("row") is not None})


def validate(frame: pd.DataFrame, settings: dict[str, Any] | None = None) -> ValidationResult:
    """`frame` comes from transform.to_canonical (with `_source_row`). Rows with any error are
    left out of `valid`; duplicate dates keep the first row."""
    errors: list[dict[str, Any]] = []
    work = frame.reset_index(drop=True)
    source_row = work["_source_row"].tolist()
    roles: set[Role] = {"input", "outcome"}
    present = [f.name for f in fields(roles=roles) if f.name in work.columns]
    data = work[present].copy()
    for f in fields(roles=roles):
        if f.required and f.name not in data.columns:
            errors.append(
                {"row": None, "column": f.name, "value": None, "message": f"{f.name} is missing"}
            )
    if any(e["row"] is None for e in errors):
        return ValidationResult(work.iloc[0:0], errors)

    bad: set[int] = set()
    try:
        to_pandera(roles, settings).validate(data, lazy=True)
    except pa_errors.SchemaErrors as exc:
        for _, case in exc.failure_cases.iterrows():
            idx = case.get("index")
            if idx is None or pd.isna(idx):
                continue
            pos = int(idx)
            bad.add(pos)
            col = case.get("column")
            errors.append(
                {
                    "row": int(source_row[pos]),
                    "column": None if col is None or pd.isna(col) else str(col),
                    "value": None
                    if pd.isna(case.get("failure_case"))
                    else str(case["failure_case"]),
                    "message": str(case.get("check")),
                }
            )
    dates = data[DATE]
    for pos in dates[dates.duplicated(keep="first") & dates.notna()].index:
        bad.add(int(pos))
        errors.append(
            {
                "row": int(source_row[pos]),
                "column": DATE,
                "value": str(dates[pos]),
                "message": "this date appears earlier in the file; only the first row is kept",
            }
        )
    keep = [i for i in range(len(work)) if i not in bad]
    return ValidationResult(work.iloc[keep].reset_index(drop=True), errors)
