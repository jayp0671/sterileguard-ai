"""Admin console endpoints (SG-25 Part A). Dept admins of the department; platform admins
for every department. Sensitive actions need a two-factor code from the last 5 minutes."""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from sg_api.core.auth import check_recent_totp
from sg_api.core.config import Settings, get_settings
from sg_api.core.roles import UUID_PATTERN, DepartmentAccess, require_role
from sg_api.db.service_client import ServiceClient
from sg_api.deps import get_gateway
from sg_api.services.admin import AdminService, DepartmentSettings, Role
from sg_api.services.supabase import Gateway

router = APIRouter(prefix="/admin", tags=["admin"])
ADMIN = require_role("dept_admin", "platform_admin")
DeptQuery = Query(..., pattern=UUID_PATTERN)


def get_admin_service(
    gw: Gateway = Depends(get_gateway), settings: Settings = Depends(get_settings)
) -> AdminService:
    svc = ServiceClient(settings) if settings.supabase_service_role_key else None
    return AdminService(gw, svc)  # type: ignore[arg-type]


class Member(BaseModel):
    user_id: UUID
    display_name: str | None = None
    email: str | None = None  # as Supabase Auth holds it
    roles: list[Role]
    last_sign_in_at: dt.datetime | None = None
    mfa_factors: int = 0


class InviteRow(BaseModel):
    id: UUID
    email: str
    role: Role
    created_at: dt.datetime
    expires_at: dt.datetime
    accepted_at: dt.datetime | None = None
    revoked_at: dt.datetime | None = None


class RolesIn(BaseModel):
    department_id: UUID
    roles: list[Role] = Field(min_length=1, max_length=4)


class RolesOut(BaseModel):
    user_id: UUID
    roles: list[Role]


class DeptIn(BaseModel):
    department_id: UUID


class MfaResetOut(BaseModel):
    user_id: UUID
    factors_removed: int
    note: str = "The user is signed out everywhere and enrolls a new authenticator at next sign-in."


class SettingsIn(BaseModel):
    department_id: UUID
    settings: DepartmentSettings


class AuditRow(BaseModel):
    id: int
    occurred_at: dt.datetime
    actor_id: UUID | None = None
    actor_role: str | None = None
    action: Literal["insert", "update", "delete"]
    entity: str
    entity_id: str | None = None
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    request_id: str | None = None


class AuditPage(BaseModel):
    items: list[AuditRow]
    next_cursor: int | None = Field(default=None, description="Pass as before_id for the next page")


def _filters(
    before_id: int | None,
    start: dt.date | None,
    end: dt.date | None,
    actor: UUID | None,
    action: str | None,
    entity: str | None,
) -> dict[str, Any]:
    return {
        "before_id": before_id,
        "start": start,
        "end": end,
        "actor": str(actor) if actor else None,
        "action": action,
        "entity": entity,
    }


@router.get("/members", response_model=list[Member])
async def list_members(
    department_id: str = DeptQuery,
    access: DepartmentAccess = Depends(ADMIN),
    svc: AdminService = Depends(get_admin_service),
) -> list[Member]:
    return [Member(**m) for m in await svc.members(access.principal.token, access.department_id)]


@router.get("/invites", response_model=list[InviteRow])
async def list_invites(
    department_id: str = DeptQuery,
    access: DepartmentAccess = Depends(ADMIN),
    svc: AdminService = Depends(get_admin_service),
) -> list[InviteRow]:
    return [InviteRow(**r) for r in await svc.invites(access.principal.token, access.department_id)]


@router.put("/members/{user_id}/roles", response_model=RolesOut)
async def set_roles(
    user_id: UUID,
    body: RolesIn,
    access: DepartmentAccess = Depends(ADMIN),
    svc: AdminService = Depends(get_admin_service),
) -> RolesOut:
    """Replace a member's roles in the department (re-auth; blocked for the last dept_admin)."""
    check_recent_totp(access.principal)
    out = await svc.set_roles(
        access.principal.token,
        access.principal.user_id,
        access.department_id,
        str(user_id),
        body.roles,
    )
    return RolesOut(**out)


@router.delete("/members/{user_id}", status_code=204)
async def remove_member(
    user_id: UUID,
    department_id: str = DeptQuery,
    access: DepartmentAccess = Depends(ADMIN),
    svc: AdminService = Depends(get_admin_service),
) -> Response:
    check_recent_totp(access.principal)
    await svc.remove(
        access.principal.token, access.principal.user_id, access.department_id, str(user_id)
    )
    return Response(status_code=204)


@router.post("/members/{user_id}/mfa-reset", response_model=MfaResetOut)
async def reset_mfa(
    user_id: UUID,
    body: DeptIn,
    access: DepartmentAccess = Depends(ADMIN),
    svc: AdminService = Depends(get_admin_service),
) -> MfaResetOut:
    """Lost-authenticator recovery: remove the member's two-factor factors (audited)."""
    check_recent_totp(access.principal)
    out = await svc.reset_mfa(
        access.principal.token, access.principal.user_id, access.department_id, str(user_id)
    )
    return MfaResetOut(**out)


@router.get("/settings", response_model=DepartmentSettings)
async def get_settings_(
    department_id: str = DeptQuery,
    access: DepartmentAccess = Depends(ADMIN),
    svc: AdminService = Depends(get_admin_service),
) -> DepartmentSettings:
    return await svc.settings(access.principal.token, access.department_id)


@router.put("/settings", response_model=DepartmentSettings)
async def put_settings(
    body: SettingsIn,
    access: DepartmentAccess = Depends(ADMIN),
    svc: AdminService = Depends(get_admin_service),
) -> DepartmentSettings:
    """Validated by DepartmentSettings; the departments audit trigger records the change."""
    return await svc.save_settings(access.principal.token, access.department_id, body.settings)


@router.get("/audit", response_model=AuditPage)
async def audit(
    department_id: str = DeptQuery,
    before_id: int | None = Query(None, ge=1),
    start: dt.date | None = Query(None, alias="from"),
    end: dt.date | None = Query(None, alias="to"),
    actor: UUID | None = None,
    action: Literal["insert", "update", "delete"] | None = None,
    entity: str | None = Query(None, pattern=r"^[a-z_]{1,40}$"),
    limit: int = Query(50, ge=1, le=200),
    access: DepartmentAccess = Depends(ADMIN),
    svc: AdminService = Depends(get_admin_service),
) -> AuditPage:
    """Newest first, cursor-paginated by id."""
    page = await svc.audit(
        access.principal.token,
        access.department_id,
        limit=limit,
        **_filters(before_id, start, end, actor, action, entity),
    )
    return AuditPage(**page)


@router.get(
    "/audit/export.csv",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}, "description": "Audit rows as CSV"}},
)
async def export_audit(
    department_id: str = DeptQuery,
    start: dt.date | None = Query(None, alias="from"),
    end: dt.date | None = Query(None, alias="to"),
    actor: UUID | None = None,
    action: Literal["insert", "update", "delete"] | None = None,
    entity: str | None = Query(None, pattern=r"^[a-z_]{1,40}$"),
    access: DepartmentAccess = Depends(ADMIN),
    svc: AdminService = Depends(get_admin_service),
) -> Response:
    """Re-auth required; the export itself is recorded in the audit log."""
    check_recent_totp(access.principal)
    text = await svc.export_audit(
        access.principal.token,
        access.principal.user_id,
        access.department_id,
        **_filters(None, start, end, actor, action, entity),
    )
    return Response(
        text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="audit-log.csv"'},
    )
