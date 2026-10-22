"""Invite rules (plan §9.1): only a dept_admin of the department or a platform_admin invites;
only a platform_admin invites a platform_admin; emails must match the organization's allowed
domains (empty list means any); invites expire after 7 days and can be resent or revoked."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sg_api.core.auth import Principal
from sg_api.core.errors import ApiError
from sg_api.schemas.invites import AppRole, InviteCreate
from sg_api.services.supabase import Gateway, Row

INVITE_TTL = timedelta(days=7)


def email_domain_allowed(email: str, allowed: list[str]) -> bool:
    if not allowed:
        return True
    domain = email.rsplit("@", 1)[-1].lower()
    return domain in {d.lower().lstrip("@") for d in allowed}


def invite_state(row: Row, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    if row.get("revoked_at"):
        return "revoked"
    if row.get("accepted_at"):
        return "accepted"
    expires = datetime.fromisoformat(str(row["expires_at"]))
    return "expired" if expires <= now else "pending"


class InviteService:
    def __init__(self, gateway: Gateway, site_url: str) -> None:
        self.gw = gateway
        self.redirect_to = f"{site_url.rstrip('/')}/accept-invite"

    async def caller_roles(self, p: Principal) -> tuple[set[str], bool]:
        """(departments where the caller is dept_admin, whether the caller is platform_admin)."""
        rows = await self.gw.select(
            p.token, "memberships", {"select": "department_id,role", "user_id": f"eq.{p.user_id}"}
        )
        admin_of = {str(r["department_id"]) for r in rows if r["role"] == AppRole.dept_admin}
        return admin_of, any(r["role"] == AppRole.platform_admin for r in rows)

    async def _authorize(self, p: Principal, department_id: str, role: str) -> None:
        admin_of, platform = await self.caller_roles(p)
        if not platform and department_id not in admin_of:
            raise ApiError(
                403, "only a dept_admin of this department or a platform_admin can invite"
            )
        if role == AppRole.platform_admin and not platform:
            raise ApiError(403, "only a platform_admin can invite a platform_admin")

    async def allowed_domains(self, p: Principal, department_id: str) -> list[str]:
        rows = await self.gw.select(
            p.token,
            "departments",
            {
                "select": "id,facilities(organizations(allowed_email_domains))",
                "id": f"eq.{department_id}",
            },
        )
        if not rows:
            raise ApiError(404, "department not found")
        org: dict[str, Any] = (rows[0].get("facilities") or {}).get("organizations") or {}
        return list(org.get("allowed_email_domains") or [])

    async def create(self, p: Principal, body: InviteCreate) -> Row:
        dept = str(body.department_id)
        await self._authorize(p, dept, body.role)
        if not email_domain_allowed(body.email, await self.allowed_domains(p, dept)):
            raise ApiError(422, "email domain is not allowed for this organization")
        row = await self.gw.insert(
            p.token,
            "invites",
            {
                "email": body.email,
                "department_id": dept,
                "role": body.role,
                "invited_by": p.user_id,
            },
        )
        try:
            await self.gw.admin_invite(body.email, self.redirect_to)
        except ApiError:
            await self.gw.update(
                p.token, "invites", {"id": f"eq.{row['id']}"}, {"revoked_at": _now_iso()}
            )
            raise
        return row

    async def _get(self, p: Principal, invite_id: str) -> Row:
        rows = await self.gw.select(p.token, "invites", {"select": "*", "id": f"eq.{invite_id}"})
        if not rows:
            raise ApiError(404, "invite not found")
        return rows[0]

    async def resend(self, p: Principal, invite_id: str) -> Row:
        row = await self._get(p, invite_id)
        state = invite_state(row)
        if state in ("accepted", "revoked"):
            raise ApiError(409, f"invite is {state}")
        await self._authorize(p, str(row["department_id"]), str(row["role"]))
        expires = (datetime.now(UTC) + INVITE_TTL).isoformat()
        updated = await self.gw.update(
            p.token, "invites", {"id": f"eq.{invite_id}"}, {"expires_at": expires}
        )
        await self.gw.admin_invite(str(row["email"]), self.redirect_to)
        return updated[0] if updated else row

    async def revoke(self, p: Principal, invite_id: str) -> Row:
        row = await self._get(p, invite_id)
        state = invite_state(row)
        if state == "accepted":
            raise ApiError(409, "invite was already accepted; remove the membership instead")
        if state == "revoked":
            return row
        updated = await self.gw.update(
            p.token, "invites", {"id": f"eq.{invite_id}"}, {"revoked_at": _now_iso()}
        )
        if not updated:
            raise ApiError(403, "not allowed")
        return updated[0]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()
