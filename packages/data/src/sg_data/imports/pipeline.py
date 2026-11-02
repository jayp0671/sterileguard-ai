"""The import pipeline end to end, short of committing (SG-21, plan §10.1).

parse -> PHI guard (identity columns dropped, PHI cells blocked) -> wide reshape -> profile ->
mapping -> transform -> validate. The result holds only aggregates and reports: findings
record entity type, column and row, never the matched text, and nothing here logs values.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from sg_data import phi
from sg_data.imports import mapping as mapping_mod
from sg_data.imports.parse import ParseReport, parse_bytes
from sg_data.imports.profile import profile
from sg_data.imports.transform import reshape_wide, to_canonical
from sg_data.imports.validate import validate


@dataclass
class ImportResult:
    content_hash: str
    column_signature: str
    parse_report: ParseReport
    phi_findings: list[dict[str, Any]]
    dropped_columns: list[str]
    blocked_rows: list[int]
    profile: list[dict[str, Any]]
    mapping: list[mapping_mod.ColumnMapping]
    transform_notes: list[str]
    errors: list[dict[str, Any]]
    valid: pd.DataFrame
    wide: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def valid_rows(self) -> int:
        return len(self.valid)

    def report(self) -> dict[str, Any]:
        """JSON-safe summary for import_jobs and the CLI (no row values beyond errors)."""
        return {
            "content_hash": self.content_hash,
            "column_signature": self.column_signature,
            "parse_report": self.parse_report.to_dict(),
            "phi_findings": self.phi_findings,
            "dropped_columns": self.dropped_columns,
            "blocked_rows": self.blocked_rows,
            "profile": self.profile,
            "mapping": [m.to_dict() for m in self.mapping],
            "transform_notes": self.transform_notes,
            "validation_report": {"valid_rows": self.valid_rows, "errors": self.errors},
            "wide": self.wide,
        }


def run(
    data: bytes,
    filename: str,
    *,
    settings: dict[str, Any] | None = None,
    templates: Mapping[str, Mapping[str, str | None]] | None = None,
    mapping_override: Mapping[str, str | None] | None = None,
    sheet: str | None = None,
    week_start: dt.date | None = None,
) -> ImportResult:
    raw, report = parse_bytes(data, filename, sheet)
    scan = phi.scan_frame(raw)
    frame, wide = reshape_wide(scan.frame, week_start)
    flagged = {f.column for f in scan.findings}
    prof = profile(frame, flagged)
    headers = [str(c) for c in frame.columns]
    sig = mapping_mod.signature(headers)
    if mapping_override is not None:
        proposal = [
            mapping_mod.ColumnMapping(
                h, mapping_override.get(h), "template" if mapping_override.get(h) else None, 100.0
            )
            for h in headers
        ]
    else:
        proposal = mapping_mod.propose(headers, templates)
    transformed = to_canonical(frame, mapping_mod.as_dict(proposal))
    checked = validate(transformed.frame, settings)
    errors = sorted(
        transformed.errors + checked.errors,
        key=lambda e: (e["row"] is None, e["row"] or 0, str(e["column"])),
    )
    blocked = sorted({int(r) for r in scan.blocked_rows})
    for row in blocked:
        errors.append(
            {
                "row": row,
                "column": None,
                "value": None,
                "message": "a text cell looked like it held identifiers and was blocked",
            }
        )
    return ImportResult(
        content_hash=hashlib.sha256(data).hexdigest(),
        column_signature=sig,
        parse_report=report,
        phi_findings=[f.to_dict() for f in scan.findings],
        dropped_columns=scan.dropped_columns,
        blocked_rows=blocked,
        profile=prof,
        mapping=proposal,
        transform_notes=transformed.notes,
        errors=errors,
        valid=checked.valid,
        wide=wide,
    )
