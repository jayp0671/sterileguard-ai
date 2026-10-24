"""Role checks for business endpoints (SG-11, plan §2.2, §7.1).

`require_role(*roles)` resolves the department from the path, the query string or the JSON
body, loads the caller's memberships with their own token (RLS applies, 60 s cache), and:
- returns 404 when the caller is not a member, so a department's existence is not leaked;
- returns 403 `forbidden_role` naming the required roles when the role is missing.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from cachetools import TTLCache
from fastapi import Depends, Request

from sg_api.core.auth import Principal
from sg_api.core.errors import ApiError
from sg_api.deps import current_user, get_gateway
from sg_api.services.supabase import Gateway

FORBIDDEN_ROLE = "https://sterileguard.dev/problems/forbidden-role"
ALL_ROLES = ("technician", "supervisor", "dept_admin", "data_steward", "platform_admin")

_memberships: TTLCache[str, list[dict[str, Any]]] = TTLCache(maxsize=2048, ttl=60)


async def get_memberships(principal: Principal, gw: Gateway) -> list[dict[str, Any]]:
    """The caller's own membership rows, read with their token. Cached 60 s per user."""
    cached = _memberships.get(principal.user_id)
    if cached is not None:
        return cached
    rows = await gw.select(
        principal.token,
        "memberships",
        {"select": "department_id,role", "user_id": f"eq.{principal.user_id}"},
    )
    _memberships[principal.user_id] = rows
    return rows


def clear_membership_cache() -> None:
    _memberships.clear()


@dataclass(frozen=True)
class DepartmentAccess:
    principal: Principal
    department_id: str
    roles: frozenset[str]


async def _department_id(request: Request) -> str | None:
    if dept := request.path_params.get("department_id"):
        return str(dept)
    if dept := request.query_params.get("department_id"):
        return dept
    if request.method in ("POST", "PUT", "PATCH"):
        try:
            body = json.loads(await request.body() or b"{}")
        except ValueError:
            return None
        if isinstance(body, dict) and isinstance(body.get("department_id"), str):
            return str(body["department_id"])
    return None


def require_role(*roles: str) -> Callable[..., Awaitable[DepartmentAccess]]:
    needed = frozenset(roles)

    async def dependency(
        request: Request,
        principal: Principal = Depends(current_user),
        gw: Gateway = Depends(get_gateway),
    ) -> DepartmentAccess:
        dept = await _department_id(request)
        if not dept:
            raise ApiError(422, "department_id is required")
        rows = await get_memberships(principal, gw)
        mine = frozenset(str(r["role"]) for r in rows if str(r["department_id"]) == dept)
        platform = any(str(r["role"]) == "platform_admin" for r in rows)
        if not mine and not platform:
            raise ApiError(404, "department not found")
        held = mine | ({"platform_admin"} if platform else frozenset())
        if not held & needed:
            raise ApiError(
                403,
                f"this action needs one of these roles: {', '.join(sorted(needed))}",
                type_=FORBIDDEN_ROLE,
            )
        return DepartmentAccess(principal=principal, department_id=dept, roles=held)

    return dependency
