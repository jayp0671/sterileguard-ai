"""Imports review API (SG-24, plan §10.1). Data stewards and department admins only."""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from sg_api.core.errors import ApiError
from sg_api.core.roles import UUID_PATTERN, DepartmentAccess, require_role
from sg_api.deps import get_gateway
from sg_api.services.imports import MAX_BYTES, ImportService, field_options
from sg_api.services.supabase import Gateway

router = APIRouter(prefix="/imports", tags=["imports"])
STEWARDS = require_role("data_steward", "dept_admin")
FileParam = File(..., description="CSV or Excel, at most 10 MB")
DeptQuery = Query(..., pattern=UUID_PATTERN, description="Department the import belongs to")

Status = Literal["uploaded", "parsed", "mapped", "validated", "committed", "failed", "cancelled"]
Method = Literal["exact", "synonym", "fuzzy", "template", "ai", "manual"]


class PhiSummary(BaseModel):
    columns_removed: int = 0
    cells_blocked: int = 0
    rows_flagged: int = 0


class ParseSummary(BaseModel):
    file_type: str | None = None
    sheet: str | None = None
    sheets: list[str] = []
    header_rows: list[int] = []
    rows: int = 0
    columns: int = 0
    wide: bool = False
    transform_notes: list[str] = []
    error: str | None = None


class ImportColumn(BaseModel):
    column: str
    field: str | None
    suggested_field: str | None = None
    method: Method | None = None
    confidence: float = Field(ge=0, le=1)
    uncertain: bool = False
    dtype: str
    samples: list[str] = Field(default_factory=list, max_length=3)
    phi_flagged: bool = False


class ImportError_(BaseModel):
    row: int | None
    column: str | None
    value: str | None
    message: str
    kind: Literal["invalid", "blocked"] = "invalid"


class PreviewCell(BaseModel):
    value: Any = None
    original: str | None = None
    changed: bool = False
    hidden: bool = False


class PreviewRow(BaseModel):
    row: int
    cells: dict[str, PreviewCell]


class Validation(BaseModel):
    valid_rows: int = 0
    invalid_rows: int = 0
    errors: list[ImportError_] = []
    preview: list[PreviewRow] = []


class ImportSummary(BaseModel):
    id: UUID
    department_id: UUID
    original_filename: str
    status: Status
    rows_committed: int | None = None
    created_by_me: bool = False
    created_at: dt.datetime
    updated_at: dt.datetime


class ImportJob(ImportSummary):
    parse: ParseSummary | None = None
    phi: PhiSummary = PhiSummary()
    columns: list[ImportColumn] = []
    validation: Validation = Validation()
    file_available: bool = False


class FieldOption(BaseModel):
    name: str
    label: str
    description: str
    unit: str
    tier: int
    required: bool


class MappingPatch(BaseModel):
    department_id: UUID
    mapping: dict[str, str | None] = Field(
        description="Source column to schema field (null to leave the column out)"
    )


class CommitBody(BaseModel):
    department_id: UUID
    overwrite: bool = Field(
        default=False, description="Replace existing real days (dept_admin only; audited)"
    )


class DeptBody(BaseModel):
    department_id: UUID


class CommitOut(BaseModel):
    import_job_id: UUID
    dataset_id: UUID | None
    rows_committed: int
    plans: int
    actuals: int
    skipped_dates: list[dt.date] = []
    already_committed: bool = False


class TemplateOut(BaseModel):
    id: UUID
    column_signature: str


def get_import_service(request: Request, gw: Gateway = Depends(get_gateway)) -> ImportService:
    suggester = getattr(request.app.state, "mapping_suggester", None)
    return ImportService(gw, suggester)  # type: ignore[arg-type]


def summary(row: dict[str, Any], user_id: str) -> ImportSummary:
    return ImportSummary(**row, created_by_me=str(row.get("created_by")) == user_id)


def to_job(row: dict[str, Any], user_id: str) -> ImportJob:
    parse = row.get("parse_report") or None
    validation = row.get("validation_report") or {}
    return ImportJob(
        **summary(row, user_id).model_dump(),
        parse=ParseSummary(**parse) if parse else None,
        phi=PhiSummary(**((parse or {}).get("phi") or {})),
        columns=[ImportColumn(**c) for c in row.get("mapping") or [] if "dtype" in c],
        validation=Validation(**validation),
        file_available=bool(row.get("storage_path")),
    )


@router.get("/fields", response_model=list[FieldOption])
async def list_fields(
    department_id: str = DeptQuery, access: DepartmentAccess = Depends(STEWARDS)
) -> list[FieldOption]:
    """Schema fields an import column can map to (for the mapping select)."""
    return [FieldOption(**f) for f in field_options()]


@router.post("", response_model=ImportJob, status_code=201)
async def upload(
    file: UploadFile = FileParam,
    department_id: str = DeptQuery,
    access: DepartmentAccess = Depends(STEWARDS),
    svc: ImportService = Depends(get_import_service),
) -> ImportJob:
    """Upload a file, then parse, PHI-guard, map and validate it. Nothing is committed."""
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ApiError(413, "the file is larger than 10 MB")
    row = await svc.create(
        access.principal.token,
        access.principal.user_id,
        access.department_id,
        file.filename or "upload",
        data,
    )
    return to_job(row, access.principal.user_id)


@router.get("", response_model=list[ImportSummary])
async def history(
    department_id: str = DeptQuery,
    access: DepartmentAccess = Depends(STEWARDS),
    svc: ImportService = Depends(get_import_service),
) -> list[ImportSummary]:
    rows = await svc.list(access.principal.token, access.department_id)
    return [summary(r, access.principal.user_id) for r in rows]


@router.get("/{job_id}", response_model=ImportJob)
async def get_job(
    job_id: UUID,
    department_id: str = DeptQuery,
    access: DepartmentAccess = Depends(STEWARDS),
    svc: ImportService = Depends(get_import_service),
) -> ImportJob:
    row = await svc.get(access.principal.token, access.department_id, str(job_id))
    return to_job(row, access.principal.user_id)


@router.patch("/{job_id}/mapping", response_model=ImportJob)
async def remap(
    job_id: UUID,
    body: MappingPatch,
    access: DepartmentAccess = Depends(STEWARDS),
    svc: ImportService = Depends(get_import_service),
) -> ImportJob:
    """Change column mappings and validate again."""
    row = await svc.remap(access.principal.token, access.department_id, str(job_id), body.mapping)
    return to_job(row, access.principal.user_id)


@router.post("/{job_id}/commit", response_model=CommitOut)
async def commit(
    job_id: UUID,
    body: CommitBody,
    access: DepartmentAccess = Depends(STEWARDS),
    svc: ImportService = Depends(get_import_service),
) -> CommitOut:
    """Write the valid rows as real data (audited). Existing real days are skipped unless a
    department admin sets overwrite."""
    if body.overwrite and "dept_admin" not in access.roles:
        raise ApiError(403, "only a department admin may overwrite existing days")
    out = await svc.commit(
        access.principal.token,
        access.principal.user_id,
        access.department_id,
        str(job_id),
        body.overwrite,
    )
    return CommitOut(**out)


@router.post("/{job_id}/cancel", response_model=ImportSummary)
async def cancel(
    job_id: UUID,
    body: DeptBody,
    access: DepartmentAccess = Depends(STEWARDS),
    svc: ImportService = Depends(get_import_service),
) -> ImportSummary:
    row = await svc.cancel(access.principal.token, access.department_id, str(job_id))
    return summary(row, access.principal.user_id)


@router.post("/{job_id}/template", response_model=TemplateOut, status_code=201)
async def save_template(
    job_id: UUID,
    body: DeptBody,
    access: DepartmentAccess = Depends(STEWARDS),
    svc: ImportService = Depends(get_import_service),
) -> TemplateOut:
    """Save this file's mapping so the next file with the same columns maps itself."""
    row = await svc.save_template(
        access.principal.token, access.principal.user_id, access.department_id, str(job_id)
    )
    return TemplateOut(**row)


@router.get(
    "/{job_id}/rejected.csv",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}, "description": "Rejected rows"}},
)
async def rejected(
    job_id: UUID,
    department_id: str = DeptQuery,
    access: DepartmentAccess = Depends(STEWARDS),
    svc: ImportService = Depends(get_import_service),
) -> Response:
    text = await svc.rejected_csv(access.principal.token, access.department_id, str(job_id))
    return Response(
        text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="rejected-{job_id}.csv"'},
    )
