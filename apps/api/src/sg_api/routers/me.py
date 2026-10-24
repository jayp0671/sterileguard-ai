"""GET /v1/me (SG-10): who the caller is and where they work. The app shell filters its
sidebar by these roles. Reads run with the caller's token, so RLS decides what is visible."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from sg_api.core.auth import Principal
from sg_api.deps import current_user, get_gateway
from sg_api.services.supabase import Gateway

router = APIRouter(tags=["me"])

AppRole = Literal["technician", "supervisor", "dept_admin", "data_steward", "platform_admin"]


class Membership(BaseModel):
    department_id: str
    department_name: str
    roles: list[AppRole]


class Me(BaseModel):
    id: str
    display_name: str | None
    locale: str
    theme: Literal["system", "light", "dark"]
    aal: str
    memberships: list[Membership]


@router.get("/me", response_model=Me)
async def me(
    principal: Principal = Depends(current_user), gw: Gateway = Depends(get_gateway)
) -> Me:
    profiles = await gw.select(
        principal.token,
        "profiles",
        {"select": "display_name,locale,theme", "user_id": f"eq.{principal.user_id}"},
    )
    rows = await gw.select(
        principal.token,
        "memberships",
        {"select": "department_id,role,departments(name)", "user_id": f"eq.{principal.user_id}"},
    )
    by_dept: dict[str, Membership] = {}
    for row in rows:
        dept = str(row["department_id"])
        name = (row.get("departments") or {}).get("name") or "Department"
        entry = by_dept.setdefault(
            dept, Membership(department_id=dept, department_name=name, roles=[])
        )
        entry.roles.append(row["role"])
    profile = profiles[0] if profiles else {}
    return Me(
        id=principal.user_id,
        display_name=profile.get("display_name"),
        locale=profile.get("locale") or "en",
        theme=profile.get("theme") or "system",
        aal=principal.aal,
        memberships=sorted(by_dept.values(), key=lambda m: m.department_name),
    )
