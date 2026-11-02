"""Commit validated rows (SG-21, plan §10.1 step 9).

Rows load into shift_plans and shift_actuals with source = 'real', under a new datasets row
per import that points at the import job (lineage: row -> dataset -> import job). Dates that
already have a real row are skipped unless overwrite is set (dept_admin only, audited by the
table triggers). Committing the same file again (same content hash) changes nothing.

The backend is a protocol: the CLI writes through Postgres, tests use InMemoryBackend.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

import pandas as pd

from sg_data.defaults import default_for
from sg_data.imports.transform import DATE, TARGET
from sg_data.schema import TIER2_INPUTS, db_columns


@dataclass
class CommitResult:
    import_job_id: str
    dataset_id: str | None
    rows_committed: int
    plans: int
    actuals: int
    skipped_dates: list[str] = field(default_factory=list)
    already_committed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CommitBackend(Protocol):
    def committed_job(self, department_id: str, content_hash: str) -> dict[str, Any] | None: ...
    def existing_dates(self, department_id: str, dates: list[dt.date]) -> set[dt.date]: ...
    def write(
        self,
        dataset: dict[str, Any],
        plans: list[dict[str, Any]],
        actuals: list[dict[str, Any]],
        overwrite: bool,
    ) -> None: ...


def _clean(v: Any) -> Any:
    if v is None or (isinstance(v, float) and pd.isna(v)) or v is pd.NA:
        return None
    if hasattr(v, "item"):  # numpy scalars
        return v.item()
    return v


def build_rows(
    valid: pd.DataFrame,
    department_id: str,
    settings: dict[str, Any],
    dataset_id: str,
    created_by: str | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Plans for every row (Tier 2 gaps from settings, flagged __missing) and actuals for rows
    that carry overtime. Imported actuals are approved: approving the import is the review."""
    plan_cols = [c for c in db_columns("shift_plans") if not c.endswith("__missing")]
    actual_cols = list(db_columns("shift_actuals"))
    now = dt.datetime.now(dt.UTC)
    plans: list[dict[str, Any]] = []
    actuals: list[dict[str, Any]] = []
    for rec in valid.to_dict("records"):
        day = rec[DATE]
        p = {c: _clean(rec.get(DATE if c == "plan_date" else c)) for c in plan_cols}
        for name in TIER2_INPUTS:
            missing = p.get(name) is None
            p[f"{name}__missing"] = missing
            if missing:
                p[name] = default_for(name, settings)
        p.update(
            department_id=department_id,
            plan_date=day,
            source="real",
            status="final",
            dataset_id=dataset_id,
            created_by=created_by,
        )
        plans.append(p)
        if _clean(rec.get(TARGET)) is not None:
            a = {c: _clean(rec.get(DATE if c == "shift_date" else c)) for c in actual_cols}
            a.update(
                department_id=department_id,
                shift_date=day,
                source="real",
                status="approved",
                approved_at=now,
                dataset_id=dataset_id,
                created_by=created_by,
            )
            actuals.append(a)
    return plans, actuals


def commit(
    backend: CommitBackend,
    valid: pd.DataFrame,
    *,
    department_id: str,
    settings: dict[str, Any],
    import_job_id: str,
    content_hash: str,
    filename: str,
    created_by: str | None = None,
    overwrite: bool = False,
) -> CommitResult:
    previous = backend.committed_job(department_id, content_hash)
    if previous is not None:
        return CommitResult(
            import_job_id=str(previous["id"]),
            dataset_id=previous.get("dataset_id"),
            rows_committed=0,
            plans=0,
            actuals=0,
            already_committed=True,
        )
    dates = [d for d in valid[DATE].tolist() if d is not None]
    existing = set() if overwrite else backend.existing_dates(department_id, dates)
    keep = valid[~valid[DATE].isin(existing)]
    dataset_id = str(uuid.uuid4())
    plans, actuals = build_rows(keep, department_id, settings, dataset_id, created_by)
    dataset = {
        "id": dataset_id,
        "department_id": department_id,
        "source": "real",
        "name": f"import {filename}",
        "row_count": len(plans),
        "content_hash": content_hash,
        "import_job_id": import_job_id,
        "created_by": created_by,
    }
    if plans:
        backend.write(dataset, plans, actuals, overwrite)
    return CommitResult(
        import_job_id=import_job_id,
        dataset_id=dataset_id if plans else None,
        rows_committed=len(plans),
        plans=len(plans),
        actuals=len(actuals),
        skipped_dates=sorted(d.isoformat() for d in existing),
    )


class InMemoryBackend:
    """For tests and dry runs: the same rules without a database."""

    def __init__(self) -> None:
        self.datasets: list[dict[str, Any]] = []
        self.plans: dict[tuple[str, dt.date], dict[str, Any]] = {}
        self.actuals: dict[tuple[str, dt.date], dict[str, Any]] = {}
        self.jobs: dict[tuple[str, str], dict[str, Any]] = {}

    def committed_job(self, department_id: str, content_hash: str) -> dict[str, Any] | None:
        return self.jobs.get((department_id, content_hash))

    def existing_dates(self, department_id: str, dates: list[dt.date]) -> set[dt.date]:
        return {d for d in dates if (department_id, d) in self.plans}

    def write(
        self,
        dataset: dict[str, Any],
        plans: list[dict[str, Any]],
        actuals: list[dict[str, Any]],
        overwrite: bool,
    ) -> None:
        self.datasets.append(dataset)
        dept = dataset["department_id"]
        for p in plans:
            self.plans[(dept, p["plan_date"])] = p
        for a in actuals:
            self.actuals[(dept, a["shift_date"])] = a
        self.jobs[(dept, dataset["content_hash"])] = {
            "id": dataset["import_job_id"],
            "dataset_id": dataset["id"],
        }
