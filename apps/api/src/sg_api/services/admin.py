"""Admin console (SG-25 Part A, plan §2.2): members, roles, factor reset, settings, audit log.

Role checks run first (require_role: dept_admin of the department, or platform admin).
Membership changes, settings and the audit log go through the admin's own token, so RLS and
the audit triggers apply. The service role is used only where no user token can work: reading
members' email, last sign-in and factor count from Supabase Auth, profiles' display names,
and deleting a locked-out user's factors (the recovery path, since Supabase has no recovery
codes). A reset and an audit export each insert an admin_actions row, which the audit
trigger records (migration 0014).
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from sg_api.core.errors import ApiError
from sg_api.core.logging import get_logger
from sg_api.db.service_client import ServiceClient
from sg_api.services.supabase import Gateway, Row

log = get_logger("sg_api.audit")

Role = Literal["technician", "supervisor", "dept_admin", "data_steward", "platform_admin"]
AUDIT_PAGE = 50
AUDIT_COLUMNS = "id,occurred_at,actor_id,actor_role,action,entity,entity_id,before,after,request_id"
EXPORT_MAX = 5000
HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"


class AdminGateway(Gateway, Protocol):
    async def delete(self, token: str, table: str, params: dict[str, str]) -> list[Row]: ...


# ---------------------------------------------------------------------------------------------
# Department settings (validated on the API, stored in departments.settings)
# ---------------------------------------------------------------------------------------------


class ShiftWindow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: Literal["morning", "aft_11", "aft_13", "aft_15"]
    start: str = Field(pattern=HHMM)
    end: str = Field(pattern=HHMM)
    default_staff: int = Field(ge=0, le=20)


class DepartmentSettings(BaseModel):
    """The editable part of departments.settings. Unknown keys already stored (for example
    burden_thresholds from SG-29) are kept as they are."""

    model_config = ConfigDict(extra="forbid")
    shift_windows: list[ShiftWindow] = Field(min_length=4, max_length=4)
    outside_support_default: int = Field(ge=0, le=20)
    outside_support_until: str = Field(pattern=HHMM)
    washers: int = Field(ge=0, le=10)
    sterilizers: int = Field(ge=0, le=10)
    mf_cases_default: int = Field(ge=0, le=80)
    ot_available_default: int = Field(ge=0, le=20)
    student_clinic_sessions_default: int = Field(ge=0, le=40)
    alert_threshold_hours: float | None = Field(default=None, ge=0, le=60)
    retention_days_drafts: int = Field(ge=7, le=365)

    @field_validator("shift_windows")
    @classmethod
    def _one_of_each(cls, v: list[ShiftWindow]) -> list[ShiftWindow]:
        if sorted(w.key for w in v) != ["aft_11", "aft_13", "aft_15", "morning"]:
            raise ValueError("needs exactly one morning, aft_11, aft_13 and aft_15 window")
        for w in v:
            if w.end <= w.start:
                raise ValueError(f"{w.key} ends before it starts")
        return v


DEFAULT_SETTINGS: dict[str, Any] = {
    "shift_windows": [
        {"key": "morning", "start": "07:00", "end": "15:00", "default_staff": 3},
        {"key": "aft_11", "start": "11:00", "end": "19:00", "default_staff": 3},
        {"key": "aft_13", "start": "13:00", "end": "21:00", "default_staff": 1},
        {"key": "aft_15", "start": "15:00", "end": "23:00", "default_staff": 2},
    ],
    "outside_support_default": 2,
    "outside_support_until": "20:00",
    "washers": 2,
    "sterilizers": 2,
    "mf_cases_default": 20,
    "ot_available_default": 2,
    "student_clinic_sessions_default": 4,
    "alert_threshold_hours": None,
    "retention_days_drafts": 90,
}


def editable(settings: dict[str, Any]) -> DepartmentSettings:
    merged = {**DEFAULT_SETTINGS, **{k: v for k, v in settings.items() if k in DEFAULT_SETTINGS}}
    return DepartmentSettings(**merged)


# ---------------------------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------------------------


class AdminService:
    def __init__(self, gw: AdminGateway, service: ServiceClient | None) -> None:
        self.gw = gw
        self.service = service

    def _svc(self) -> ServiceClient:
        if self.service is None:
            raise ApiError(503, "admin features need the service role key on the API")
        return self.service

    async def _memberships(self, token: str, dept: str) -> list[Row]:
        return await self.gw.select(
            token,
            "memberships",
            {"select": "user_id,department_id,role,created_at", "department_id": f"eq.{dept}"},
        )

    async def members(self, token: str, dept: str) -> list[Row]:
        rows = await self._memberships(token, dept)
        by_user: dict[str, list[str]] = {}
        for r in rows:
            by_user.setdefault(str(r["user_id"]), []).append(str(r["role"]))
        names: dict[str, str | None] = {}
        out: list[Row] = []
        svc = self.service
        if svc is not None and by_user:
            ids = ",".join(by_user)
            for p in await svc.select(
                "profiles", {"select": "user_id,display_name", "user_id": f"in.({ids})"}
            ):
                names[str(p["user_id"])] = p.get("display_name")
        for uid, user_roles in sorted(by_user.items()):
            user = await svc.auth_user(uid) if svc is not None else None
            factors = [
                f for f in (user or {}).get("factors") or [] if f.get("status") == "verified"
            ]
            out.append(
                {
                    "user_id": uid,
                    "display_name": names.get(uid),
                    "email": (user or {}).get("email"),
                    "roles": sorted(user_roles),
                    "last_sign_in_at": (user or {}).get("last_sign_in_at"),
                    "mfa_factors": len(factors),
                }
            )
        return out

    async def invites(self, token: str, dept: str) -> list[Row]:
        return await self.gw.select(
            token,
            "invites",
            {"select": "*", "department_id": f"eq.{dept}", "order": "created_at.desc"},
        )

    @staticmethod
    def _admins_after(rows: list[Row], user_id: str, new_roles: set[str]) -> int:
        admins = {str(r["user_id"]) for r in rows if r["role"] == "dept_admin"}
        admins.discard(user_id)
        if "dept_admin" in new_roles:
            admins.add(user_id)
        return len(admins)

    async def set_roles(
        self, token: str, actor: str, dept: str, user_id: str, roles: list[Role]
    ) -> Row:
        wanted: set[str] = set(roles)
        if "platform_admin" in wanted:
            raise ApiError(403, "platform admin is granted by the platform team, not here")
        rows = await self._memberships(token, dept)
        current = {str(r["role"]) for r in rows if str(r["user_id"]) == user_id}
        if not current:
            raise ApiError(404, "member not found")
        if self._admins_after(rows, user_id, wanted) == 0:
            raise ApiError(409, "a department needs at least one dept_admin")
        for new_role in sorted(wanted - current):
            await self.gw.insert(
                token, "memberships", {"user_id": user_id, "department_id": dept, "role": new_role}
            )
        for old_role in sorted(current - wanted - {"platform_admin"}):
            await self.gw.delete(
                token,
                "memberships",
                {
                    "user_id": f"eq.{user_id}",
                    "department_id": f"eq.{dept}",
                    "role": f"eq.{old_role}",
                },
            )
        log.info("member_roles_changed", user_id=actor, target=user_id, department_id=dept)
        return {"user_id": user_id, "roles": sorted(wanted | (current & {"platform_admin"}))}

    async def remove(self, token: str, actor: str, dept: str, user_id: str) -> None:
        rows = await self._memberships(token, dept)
        if not any(str(r["user_id"]) == user_id for r in rows):
            raise ApiError(404, "member not found")
        if self._admins_after(rows, user_id, set()) == 0:
            raise ApiError(409, "a department needs at least one dept_admin")
        await self.gw.delete(
            token, "memberships", {"user_id": f"eq.{user_id}", "department_id": f"eq.{dept}"}
        )
        log.info("member_removed", user_id=actor, target=user_id, department_id=dept)

    async def reset_mfa(self, token: str, actor: str, dept: str, user_id: str) -> Row:
        rows = await self._memberships(token, dept)
        if not any(str(r["user_id"]) == user_id for r in rows):
            raise ApiError(404, "member not found")
        svc = self._svc()
        factors = await svc.auth_factors(user_id)
        for f in factors:
            await svc.delete_factor(user_id, str(f["id"]))
        # The audit record: inserted with the admin's token, recorded by the audit trigger.
        await self.gw.insert(
            token,
            "admin_actions",
            {
                "department_id": dept,
                "actor_id": actor,
                "action": "mfa_reset",
                "target_user_id": user_id,
                "detail": {"factors_removed": len(factors)},
            },
        )
        log.info("mfa_reset", user_id=actor, target=user_id, factors=len(factors))
        return {"user_id": user_id, "factors_removed": len(factors)}

    async def settings(self, token: str, dept: str) -> DepartmentSettings:
        rows = await self.gw.select(
            token, "departments", {"select": "settings", "id": f"eq.{dept}"}
        )
        if not rows:
            raise ApiError(404, "department not found")
        return editable(dict(rows[0].get("settings") or {}))

    async def save_settings(
        self, token: str, dept: str, body: DepartmentSettings
    ) -> DepartmentSettings:
        rows = await self.gw.select(
            token, "departments", {"select": "settings", "id": f"eq.{dept}"}
        )
        if not rows:
            raise ApiError(404, "department not found")
        merged = {**dict(rows[0].get("settings") or {}), **body.model_dump(mode="json")}
        updated = await self.gw.update(
            token, "departments", {"id": f"eq.{dept}"}, {"settings": merged}
        )
        if not updated:
            raise ApiError(403, "not allowed")  # RLS: only dept_admin edits settings
        return editable(merged)

    @staticmethod
    def audit_params(
        dept: str,
        *,
        before_id: int | None = None,
        start: dt.date | None = None,
        end: dt.date | None = None,
        actor: str | None = None,
        action: str | None = None,
        entity: str | None = None,
        limit: int = AUDIT_PAGE,
    ) -> dict[str, str]:
        params = {
            "select": AUDIT_COLUMNS,
            "department_id": f"eq.{dept}",
            "order": "id.desc",
            "limit": str(limit),
        }
        conds = []
        if before_id is not None:
            conds.append(f"id.lt.{before_id}")
        if start is not None:
            conds.append(f"occurred_at.gte.{start.isoformat()}")
        if end is not None:
            conds.append(f"occurred_at.lt.{(end + dt.timedelta(days=1)).isoformat()}")
        if conds:
            params["and"] = f"({','.join(conds)})"
        if actor:
            params["actor_id"] = f"eq.{actor}"
        if action:
            params["action"] = f"eq.{action}"
        if entity:
            params["entity"] = f"eq.{entity}"
        return params

    async def audit(self, token: str, dept: str, **filters: Any) -> Row:
        limit = int(filters.pop("limit", AUDIT_PAGE))
        rows = await self.gw.select(
            token, "audit_log", self.audit_params(dept, limit=limit + 1, **filters)
        )
        more = len(rows) > limit
        rows = rows[:limit]
        return {"items": rows, "next_cursor": rows[-1]["id"] if more and rows else None}

    async def export_audit(self, token: str, actor_id: str, dept: str, **filters: Any) -> str:
        rows = await self.gw.select(
            token, "audit_log", self.audit_params(dept, limit=EXPORT_MAX, **filters)
        )
        await self.gw.insert(
            token,
            "admin_actions",
            {
                "department_id": dept,
                "actor_id": actor_id,
                "action": "audit_export",
                "detail": {
                    "rows": len(rows),
                    "filters": {k: str(v) for k, v in filters.items() if v is not None},
                },
            },
        )
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(
            [
                "id",
                "occurred_at",
                "actor_id",
                "actor_role",
                "action",
                "entity",
                "entity_id",
                "before",
                "after",
            ]
        )
        for r in rows:
            w.writerow(
                [
                    r["id"],
                    r["occurred_at"],
                    r.get("actor_id") or "",
                    r.get("actor_role") or "",
                    r["action"],
                    r["entity"],
                    r.get("entity_id") or "",
                    json.dumps(r.get("before"), sort_keys=True) if r.get("before") else "",
                    json.dumps(r.get("after"), sort_keys=True) if r.get("after") else "",
                ]
            )
        log.info("audit_exported", user_id=actor_id, department_id=dept, rows=len(rows))
        return buf.getvalue()
