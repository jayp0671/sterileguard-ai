"""Imports review (SG-24, plan §10.1): upload, review, remap, commit, cancel, rejected rows.

The raw file goes to the private `imports` bucket under <department>/<job>/ with the caller's
token (the bucket's folder policies apply) and is deleted on commit or cancel. Every step runs
the deterministic SG-21 pipeline again from that file, so nothing but reports is stored in
import_jobs. The commit itself is one call to public.commit_import (migration 0012,
ADR-0010), which forces the department, source and author and is audited by the triggers.

PHI rule: API responses carry counts of removed columns and blocked cells, never the values,
and flagged columns never show sample values. Dropped columns are not listed by header (a
header could itself be a name), only counted.
"""

from __future__ import annotations

import asyncio
import csv
import datetime as dt
import hashlib
import io
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from sg_api.core.errors import ApiError
from sg_api.core.logging import get_logger
from sg_api.services import plans as plan_svc
from sg_api.services.supabase import Gateway, Row, StorageGateway
from sg_data.imports import commit as commit_mod
from sg_data.imports import mapping as mapping_mod
from sg_data.imports.parse import ParseError
from sg_data.imports.pipeline import ImportResult, run
from sg_data.schema import BY_NAME

log = get_logger("sg_api.imports")

BUCKET = "imports"
MAX_BYTES = 10 * 1024 * 1024
PREVIEW_ROWS = 50
MAX_ERRORS = 500
UNCERTAIN_BELOW = 0.6
XLSX_MAGIC = b"PK\x03\x04"
XLS_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
TEXT_FIELDS = frozenset({"notes"})  # free text: never echoed in the preview
OPEN = ("uploaded", "parsed", "mapped", "validated")
JOB_COLUMNS = (
    "id,department_id,original_filename,content_hash,status,storage_path,parse_report,mapping,"
    "validation_report,phi_findings,rows_committed,created_by,approved_by,created_at,updated_at"
)


class ImportGateway(Gateway, StorageGateway):
    """The gateway imports need: PostgREST plus Storage with the caller's token."""


def check_file(filename: str, data: bytes) -> str:
    """Extension, size and magic bytes must agree. Returns the extension."""
    ext = Path(filename).suffix.lower()
    if not data:
        raise ApiError(422, "the file is empty")
    if len(data) > MAX_BYTES:
        raise ApiError(413, "the file is larger than 10 MB")
    head = data[:8]
    if ext == ".xlsx" and head.startswith(XLSX_MAGIC):
        return ext
    if ext == ".xls" and head.startswith(XLS_MAGIC):
        return ext
    if (
        ext == ".csv"
        and not head.startswith((XLSX_MAGIC, XLS_MAGIC))
        and b"\x00" not in data[:8192]
    ):
        return ext
    if ext not in (".csv", ".xlsx", ".xls"):
        raise ApiError(415, "unsupported file type; use .csv, .xlsx or .xls")
    raise ApiError(415, "the file content does not match its extension")


def safe_filename(name: str) -> str:
    base = Path(name.replace("\\", "/")).name.strip() or "upload"
    return "".join(c for c in base if c.isprintable())[:255]


def _jsonable(v: Any) -> Any:
    if v is None or v is pd.NA or (isinstance(v, float) and pd.isna(v)):
        return None
    if hasattr(v, "item"):
        v = v.item()
    if isinstance(v, dt.datetime):
        return v.date().isoformat() if v.time() == dt.time() else v.isoformat()
    if isinstance(v, dt.date):
        return v.isoformat()
    return v


def preview(result: ImportResult, limit: int = PREVIEW_ROWS) -> list[dict[str, Any]]:
    """First transformed rows; each cell has the value, the file's original text and whether
    the pipeline changed it (normalized dates, units, totals)."""
    frame: pd.DataFrame = result.extra["frame"]
    canon: pd.DataFrame = result.extra["transformed"]
    sources = {m.field: m.column for m in result.mapping if m.field}
    out: list[dict[str, Any]] = []
    for rec in canon.head(limit).to_dict("records"):
        pos = int(rec.get("_source_row", -1))
        cells: dict[str, Any] = {}
        for key, value in rec.items():
            name = str(key)
            if name.startswith("_") or name not in BY_NAME:
                continue
            if name in TEXT_FIELDS:
                cells[name] = {"value": None, "original": None, "changed": False, "hidden": True}
                continue
            src = sources.get(name)
            original = None
            if src is not None and src in frame.columns and 0 <= pos < len(frame):
                original = _jsonable(frame[src].iloc[pos])
            v = _jsonable(value)
            changed = original is not None and str(original).strip() != str(v)
            cells[name] = {
                "value": v,
                "original": None if original is None else str(original),
                "changed": changed,
                "hidden": False,
            }
        out.append({"row": pos, "cells": cells})
    return out


def phi_summary(result: ImportResult) -> dict[str, int]:
    cell_findings = [f for f in result.phi_findings if f.get("row") is not None]
    return {
        "columns_removed": len(result.dropped_columns),
        "cells_blocked": len(cell_findings),
        "rows_flagged": len(result.blocked_rows),
    }


def columns_view(result: ImportResult, suggestions: Mapping[str, Any] | None = None) -> list[Row]:
    profile = {p["column"]: p for p in result.profile}
    out: list[Row] = []
    for m in result.mapping:
        p = profile.get(m.column, {})
        flagged = bool(p.get("phi"))
        sugg = (suggestions or {}).get(m.column)
        method: str | None = m.method
        confidence = round(m.score / 100, 2) if m.field else 0.0
        field = m.field
        if field is None and sugg and sugg.get("field"):
            # An AI suggestion is shown, never applied, until a person saves the mapping.
            method, confidence = "ai", float(sugg.get("confidence", 0.0))
        out.append(
            {
                "column": m.column,
                "field": field,
                "suggested_field": sugg.get("field") if sugg and field is None else None,
                "method": method,
                "confidence": confidence,
                "uncertain": method is not None and confidence < UNCERTAIN_BELOW,
                "dtype": p.get("dtype", "empty"),
                "samples": [] if flagged else list(p.get("samples", []))[:3],
                "phi_flagged": flagged,
            }
        )
    return out


def reports(result: ImportResult, suggestions: Mapping[str, Any] | None = None) -> Row:
    """What import_jobs stores: reports and counts, no raw cells beyond error values."""
    full = result.report()
    blocked = set(result.blocked_rows)
    errors = [
        {
            **{k: e.get(k) for k in ("row", "column", "value", "message")},
            # A blocked cell is cleared and the rest of the row still imports (ADR-0009).
            "kind": "blocked" if e.get("column") is None and e.get("row") in blocked else "invalid",
        }
        for e in full["validation_report"]["errors"]
    ]
    invalid = len({e["row"] for e in errors if e["row"] is not None and e["kind"] == "invalid"})
    return {
        "parse_report": {
            **full["parse_report"],
            "wide": full["wide"],
            "transform_notes": full["transform_notes"],
            "column_signature": full["column_signature"],
            "phi": phi_summary(result),
        },
        "mapping": columns_view(result, suggestions),
        "validation_report": {
            "valid_rows": result.valid_rows,
            "invalid_rows": invalid,
            "errors": errors[:MAX_ERRORS],
            "preview": preview(result),
        },
        # Entity type, column position and row only (never the matched text).
        "phi_findings": [
            {"entity_type": f["entity_type"], "row": f.get("row")} for f in result.phi_findings
        ],
    }


class ImportService:
    def __init__(self, gw: ImportGateway, suggester: Any = None) -> None:
        self.gw = gw
        # SG-23 mapping agent: async (unmapped, profile, taken) -> {column: suggestion}
        self.suggester = suggester

    # -- helpers ---------------------------------------------------------------------------
    async def _job(self, token: str, dept: str, job_id: str) -> Row:
        rows = await self.gw.select(
            token,
            "import_jobs",
            {"select": JOB_COLUMNS, "id": f"eq.{job_id}", "department_id": f"eq.{dept}"},
        )
        if not rows:
            raise ApiError(404, "import job not found")
        return rows[0]

    async def _templates(self, token: str, dept: str) -> dict[str, dict[str, str | None]]:
        rows = await self.gw.select(
            token,
            "mapping_templates",
            {"select": "column_signature,mapping", "department_id": f"eq.{dept}"},
        )
        return {r["column_signature"]: dict(r["mapping"] or {}) for r in rows}

    async def _run(
        self,
        token: str,
        dept: str,
        job: Row,
        override: Mapping[str, str | None] | None = None,
    ) -> tuple[ImportResult, dict[str, Any]]:
        if not job.get("storage_path"):
            raise ApiError(410, "the uploaded file is no longer available; upload it again")
        data = await self.gw.storage_download(token, BUCKET, job["storage_path"])
        settings, _ = await plan_svc.department(self.gw, token, dept)
        templates = None if override is not None else await self._templates(token, dept)
        result = await asyncio.to_thread(
            run,
            data,
            job["original_filename"],
            settings=settings,
            templates=templates,
            mapping_override=override,
        )
        return result, settings

    @staticmethod
    def _saved_override(job: Row) -> dict[str, str | None]:
        return {c["column"]: c.get("field") for c in (job.get("mapping") or [])}

    async def _suggest(self, result: ImportResult) -> dict[str, Any]:
        if self.suggester is None:
            return {}
        unmapped = [m.column for m in result.mapping if m.field is None]
        if not unmapped:
            return {}
        try:
            taken = [m.field for m in result.mapping if m.field]
            out: dict[str, Any] = await self.suggester(unmapped, result.profile, taken)
        except Exception:  # the agent is optional: any failure means manual mapping
            log.warning("mapping_agent_unavailable")
            return {}
        return out

    # -- endpoints -------------------------------------------------------------------------
    async def create(self, token: str, user_id: str, dept: str, filename: str, data: bytes) -> Row:
        name = safe_filename(filename)
        ext = check_file(name, data)
        job_id = str(uuid.uuid4())
        path = f"{dept}/{job_id}/source{ext}"
        content_type = "text/csv" if ext == ".csv" else "application/octet-stream"
        job = await self.gw.insert(
            token,
            "import_jobs",
            {
                "id": job_id,
                "department_id": dept,
                "original_filename": name,
                "content_hash": hashlib.sha256(data).hexdigest(),
                "status": "uploaded",
                "created_by": user_id,
            },
        )
        await self.gw.storage_upload(token, BUCKET, path, data, content_type)
        settings, _ = await plan_svc.department(self.gw, token, dept)
        templates = await self._templates(token, dept)
        try:
            result = await asyncio.to_thread(
                run, data, name, settings=settings, templates=templates
            )
        except ParseError as exc:
            await self.gw.storage_delete(token, BUCKET, path)
            rows = await self.gw.update(
                token,
                "import_jobs",
                {"id": f"eq.{job_id}"},
                {"status": "failed", "parse_report": {"error": str(exc)}},
            )
            log.info("import_failed", job_id=job_id, reason="parse")
            return rows[0] if rows else job
        suggestions = await self._suggest(result)
        rows = await self.gw.update(
            token,
            "import_jobs",
            {"id": f"eq.{job_id}"},
            {"status": "validated", "storage_path": path, **reports(result, suggestions)},
        )
        log.info(
            "import_validated",
            job_id=job_id,
            valid_rows=result.valid_rows,
            errors=len(result.errors),
            phi_findings=len(result.phi_findings),
        )
        return rows[0]

    async def get(self, token: str, dept: str, job_id: str) -> Row:
        return await self._job(token, dept, job_id)

    async def list(self, token: str, dept: str, limit: int = 50) -> list[Row]:
        return await self.gw.select(
            token,
            "import_jobs",
            {
                "select": "id,department_id,original_filename,status,rows_committed,created_by,"
                "created_at,updated_at",
                "department_id": f"eq.{dept}",
                "order": "created_at.desc",
                "limit": str(limit),
            },
        )

    async def remap(
        self, token: str, dept: str, job_id: str, mapping: Mapping[str, str | None]
    ) -> Row:
        job = await self._job(token, dept, job_id)
        if job["status"] not in OPEN:
            raise ApiError(409, f"this import is {job['status']}")
        current = self._saved_override(job)
        unknown = set(mapping) - set(current)
        if unknown:
            raise ApiError(422, "mapping names a column the file does not have")
        bad = {f for f in mapping.values() if f is not None and f not in MAPPABLE_FIELDS}
        if bad:
            raise ApiError(422, "mapping names a field that imports cannot fill")
        merged = {**current, **mapping}
        taken = [f for f in merged.values() if f]
        if len(taken) != len(set(taken)):
            raise ApiError(422, "each field can be mapped from one column only")
        result, _ = await self._run(token, dept, job, merged)
        stored = reports(result)
        before = {c["column"]: c for c in job.get("mapping") or []}
        for col in stored["mapping"]:
            if col["column"] in mapping:
                # A person chose this one: shown as a manual mapping, never "uncertain".
                col.update(method="manual" if col["field"] else None, confidence=1.0)
                col.update(uncertain=False, suggested_field=None)
            elif prev := before.get(col["column"]):
                for key in ("method", "confidence", "uncertain", "suggested_field"):
                    col[key] = prev.get(key)
        rows = await self.gw.update(
            token, "import_jobs", {"id": f"eq.{job_id}"}, {"status": "validated", **stored}
        )
        return rows[0]

    async def commit(
        self, token: str, user_id: str, dept: str, job_id: str, overwrite: bool = False
    ) -> Row:
        job = await self._job(token, dept, job_id)
        if job["status"] not in OPEN:
            raise ApiError(409, f"this import is {job['status']}")
        result, settings = await self._run(token, dept, job, self._saved_override(job))
        plans, actuals = commit_mod.build_rows(result.valid, dept, settings, "", user_id)
        status, body = await self.gw.rpc_result(
            token,
            "commit_import",
            {
                "p_job_id": job_id,
                "p_plans": [{k: _jsonable(v) for k, v in p.items()} for p in plans],
                "p_actuals": [{k: _jsonable(v) for k, v in a.items()} for a in actuals],
                "p_overwrite": overwrite,
            },
        )
        if status >= 400:
            code = (body or {}).get("code") if isinstance(body, dict) else None
            if code == "P0002":
                raise ApiError(404, "import job not found")
            if code == "55000":
                raise ApiError(409, "this import was already committed or cancelled")
            if code == "42501":
                raise ApiError(403, "only a department admin may overwrite existing days")
            raise ApiError(422, "the database rejected the rows")
        # Save the reviewed mapping so the next file with these columns maps with no AI call.
        await self.save_template(token, user_id, dept, job_id, job=job)
        await self.gw.storage_delete(token, BUCKET, job["storage_path"])
        await self.gw.update(token, "import_jobs", {"id": f"eq.{job_id}"}, {"storage_path": None})
        log.info("import_committed", job_id=job_id, rows=body.get("rows_committed"))
        out: Row = body
        return out

    async def cancel(self, token: str, dept: str, job_id: str) -> Row:
        job = await self._job(token, dept, job_id)
        if job["status"] not in (*OPEN, "failed"):
            raise ApiError(409, f"this import is {job['status']}")
        if job.get("storage_path"):
            await self.gw.storage_delete(token, BUCKET, job["storage_path"])
        rows = await self.gw.update(
            token,
            "import_jobs",
            {"id": f"eq.{job_id}"},
            {"status": "cancelled", "storage_path": None, "rows_committed": 0},
        )
        return rows[0]

    async def save_template(
        self, token: str, user_id: str, dept: str, job_id: str, job: Row | None = None
    ) -> Row:
        job = job or await self._job(token, dept, job_id)
        sig = (job.get("parse_report") or {}).get("column_signature")
        mapping = self._saved_override(job)
        if not sig or not mapping:
            raise ApiError(409, "this import has no mapping to save")
        return await self.gw.upsert(
            token,
            "mapping_templates",
            {
                "department_id": dept,
                "column_signature": sig,
                "mapping": mapping,
                "created_by": user_id,
            },
            on_conflict="department_id,column_signature",
        )

    async def rejected_csv(self, token: str, dept: str, job_id: str) -> str:
        """Rejected rows as they were in the file after the PHI guard (identity columns dropped,
        blocked cells empty), plus an error column."""
        job = await self._job(token, dept, job_id)
        errors = (job.get("validation_report") or {}).get("errors") or []
        by_row: dict[int, list[str]] = {}
        for e in errors:
            if e.get("row") is not None and e.get("kind", "invalid") == "invalid":
                col = f"{e['column']}: " if e.get("column") else ""
                by_row.setdefault(int(e["row"]), []).append(f"{col}{e['message']}")
        frame: pd.DataFrame | None = None
        if job.get("storage_path") and by_row:
            result, _ = await self._run(token, dept, job, self._saved_override(job))
            frame = result.extra["frame"]
        buf = io.StringIO()
        writer = csv.writer(buf)
        headers = [str(c) for c in frame.columns] if frame is not None else []
        writer.writerow(["source_row", *headers, "error"])
        for row in sorted(by_row):
            values: list[Any] = []
            if frame is not None and 0 <= row < len(frame):
                values = ["" if _jsonable(v) is None else _jsonable(v) for v in frame.iloc[row]]
            writer.writerow([row + 1, *values, "; ".join(by_row[row])])
        return buf.getvalue()


MAPPABLE_FIELDS = frozenset(f.name for f in mapping_mod.MAPPABLE)


def field_options() -> list[Row]:
    return [
        {
            "name": f.name,
            "label": f.label or f.name.replace("_", " "),
            "description": f.description,
            "unit": f.unit,
            "tier": f.tier,
            "required": f.required,
        }
        for f in mapping_mod.MAPPABLE
    ]
