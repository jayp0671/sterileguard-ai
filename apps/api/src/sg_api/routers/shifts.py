"""Shift actual endpoints (SG-20, plan §7.2). Members read; technicians and above log and
submit; supervisors and department admins approve; department admins reopen with a reason."""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from sg_api.core.auth import check_recent_totp
from sg_api.core.roles import ALL_ROLES, DepartmentAccess, require_role
from sg_api.deps import get_gateway
from sg_api.services import shifts
from sg_api.services.supabase import Gateway

router = APIRouter(prefix="/shifts", tags=["shifts"])

READ = require_role(*ALL_ROLES)
LOG = require_role("technician", "supervisor", "dept_admin")
LEADS = require_role("supervisor", "dept_admin")
ADMIN = require_role("dept_admin")
DEPARTMENT = Query(..., description="Department the shift belongs to")


@router.get("", response_model=shifts.ShiftPage)
async def list_shifts(
    department_id: str = DEPARTMENT,
    from_: dt.date | None = Query(None, alias="from"),
    to: dt.date | None = None,
    status: shifts.Status | None = None,
    limit: int = Query(50, ge=1, le=shifts.PAGE_MAX),
    offset: int = Query(0, ge=0),
    access: DepartmentAccess = Depends(READ),
    gw: Gateway = Depends(get_gateway),
) -> shifts.ShiftPage:
    """Newest first, each row with the forecast for its date (p10/p50/p90) when one exists."""
    p = access.principal
    return await shifts.list_shifts(
        gw, p.token, p.user_id, access.department_id, from_, to, status, limit, offset
    )


@router.get(
    "/export",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}, "description": "CSV of the date range"}},
)
async def export_shifts(
    from_: dt.date = Query(..., alias="from"),
    to: dt.date = Query(...),
    department_id: str = DEPARTMENT,
    access: DepartmentAccess = Depends(LEADS),
    gw: Gateway = Depends(get_gateway),
) -> Response:
    """CSV export: needs a two-factor check in the last 5 minutes, and is audited."""
    check_recent_totp(access.principal)
    p = access.principal
    body = await shifts.export_csv(gw, p.token, p.user_id, access.department_id, from_, to)
    name = f"shift-actuals-{from_.isoformat()}-{to.isoformat()}.csv"
    return Response(
        body,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.post("", response_model=shifts.ShiftOut, status_code=201)
async def log_shift(
    body: shifts.ShiftCreate,
    access: DepartmentAccess = Depends(LOG),
    gw: Gateway = Depends(get_gateway),
) -> shifts.ShiftOut:
    """A draft for a date on or before today (409 actual-exists if the date is logged). With
    `plan`, supervisors backfill a real past day: a final plan is created too."""
    payload: Any = body
    p = access.principal
    return await shifts.create(gw, p.token, p.user_id, access.department_id, access.roles, payload)


@router.get("/{shift_id}", response_model=shifts.ShiftDetail)
async def get_shift(
    shift_id: str,
    department_id: str = DEPARTMENT,
    access: DepartmentAccess = Depends(READ),
    gw: Gateway = Depends(get_gateway),
) -> shifts.ShiftDetail:
    """One row; department admins also get its audit trail."""
    p = access.principal
    return await shifts.detail(gw, p.token, p.user_id, access.department_id, access.roles, shift_id)


@router.patch("/{shift_id}", response_model=shifts.ShiftOut)
async def edit_shift(
    shift_id: str,
    body: shifts.ShiftPatch,
    access: DepartmentAccess = Depends(LOG),
    gw: Gateway = Depends(get_gateway),
) -> shifts.ShiftOut:
    """The author edits while draft or submitted; supervisors edit any row not approved."""
    payload: Any = body
    p = access.principal
    return await shifts.update(
        gw, p.token, p.user_id, access.department_id, access.roles, shift_id, payload
    )


@router.post("/{shift_id}/submit", response_model=shifts.ShiftOut)
async def submit_shift(
    shift_id: str,
    body: shifts.DepartmentIn,
    access: DepartmentAccess = Depends(LOG),
    gw: Gateway = Depends(get_gateway),
) -> shifts.ShiftOut:
    p = access.principal
    return await shifts.transition(
        gw, p.token, p.user_id, access.department_id, access.roles, shift_id, "submit"
    )


@router.post("/{shift_id}/approve", response_model=shifts.ShiftOut)
async def approve_shift(
    shift_id: str,
    body: shifts.DepartmentIn,
    access: DepartmentAccess = Depends(LEADS),
    gw: Gateway = Depends(get_gateway),
) -> shifts.ShiftOut:
    """Supervisors and department admins approve a submitted row; it is then locked."""
    p = access.principal
    return await shifts.transition(
        gw, p.token, p.user_id, access.department_id, access.roles, shift_id, "approve"
    )


@router.post("/{shift_id}/reopen", response_model=shifts.ShiftOut)
async def reopen_shift(
    shift_id: str,
    body: shifts.ReopenIn,
    access: DepartmentAccess = Depends(ADMIN),
    gw: Gateway = Depends(get_gateway),
) -> shifts.ShiftOut:
    """Department admins only. The reason is stored on the row, so the audit row keeps it."""
    p = access.principal
    return await shifts.transition(
        gw,
        p.token,
        p.user_id,
        access.department_id,
        access.roles,
        shift_id,
        "reopen",
        reason=body.reason,
    )
