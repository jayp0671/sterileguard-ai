"""Policy acceptance and cookie consent (SG-25 Part B and C, plan §14.4).

Current versions of the Terms and the Privacy Policy live here and in the frontmatter of
apps/web/src/content/legal/en/*.md; `sg compliance check` fails if they disagree. Users accept
both after sign-in and again whenever either version changes.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from sg_api.core.auth import Principal, optional_principal
from sg_api.core.config import Settings, get_settings
from sg_api.core.errors import ApiError
from sg_api.db.service_client import ServiceClient
from sg_api.deps import current_user, get_gateway
from sg_api.services.supabase import Gateway

router = APIRouter(tags=["compliance"])

POLICY_VERSIONS: dict[str, str] = {"terms": "1.0.0", "privacy": "1.0.0"}
COOKIE_POLICY_VERSION = "1.0.0"
SEMVER = r"^\d+\.\d+\.\d+$"


class PolicyStatus(BaseModel):
    policy: Literal["terms", "privacy"]
    version: str
    accepted: bool
    accepted_at: dt.datetime | None = None


class PoliciesOut(BaseModel):
    policies: list[PolicyStatus]
    all_accepted: bool


class AcceptIn(BaseModel):
    policy: Literal["terms", "privacy"]
    version: str = Field(pattern=SEMVER)


class ConsentIn(BaseModel):
    anon_id: str | None = Field(
        default=None, min_length=8, max_length=64, pattern=r"^[A-Za-z0-9-]+$"
    )
    version: str = Field(pattern=SEMVER)
    analytics: bool = False
    gpc: bool = False


class ConsentOut(BaseModel):
    recorded: bool
    analytics: bool


async def _status(gw: Gateway, p: Principal) -> PoliciesOut:
    rows = await gw.select(
        p.token,
        "policy_acceptances",
        {"select": "policy,version,accepted_at", "user_id": f"eq.{p.user_id}"},
    )
    have = {(r["policy"], r["version"]): r["accepted_at"] for r in rows}
    out = [
        PolicyStatus(
            policy=pol,  # type: ignore[arg-type]
            version=ver,
            accepted=(pol, ver) in have,
            accepted_at=have.get((pol, ver)),
        )
        for pol, ver in POLICY_VERSIONS.items()
    ]
    return PoliciesOut(policies=out, all_accepted=all(s.accepted for s in out))


@router.get("/me/policies", response_model=PoliciesOut)
async def my_policies(
    p: Principal = Depends(current_user), gw: Gateway = Depends(get_gateway)
) -> PoliciesOut:
    """Which current policy versions the caller has accepted."""
    return await _status(gw, p)


@router.post("/me/policies", response_model=PoliciesOut)
async def accept_policy(
    body: AcceptIn, p: Principal = Depends(current_user), gw: Gateway = Depends(get_gateway)
) -> PoliciesOut:
    """Record acceptance of the current version (audited by the table trigger)."""
    if POLICY_VERSIONS[body.policy] != body.version:
        raise ApiError(409, f"the current {body.policy} version is {POLICY_VERSIONS[body.policy]}")
    try:
        await gw.insert(
            p.token,
            "policy_acceptances",
            {"user_id": p.user_id, "policy": body.policy, "version": body.version},
        )
    except ApiError as exc:
        if exc.status != 409:  # already accepted is fine
            raise
    return await _status(gw, p)


@router.post("/consents", response_model=ConsentOut, status_code=201)
async def record_consent(
    body: ConsentIn,
    p: Principal | None = Depends(optional_principal),
    settings: Settings = Depends(get_settings),
) -> ConsentOut:
    """Log a cookie choice against the cookie policy version. Global Privacy Control means no
    analytics, whatever the body says. Works before sign-in (anonymous id from the browser)."""
    if body.version != COOKIE_POLICY_VERSION:
        raise ApiError(409, f"the current cookie policy version is {COOKIE_POLICY_VERSION}")
    if p is None and not body.anon_id:
        raise ApiError(422, "anon_id is required before sign-in")
    analytics = body.analytics and not body.gpc
    if not settings.supabase_service_role_key:
        return ConsentOut(recorded=False, analytics=analytics)
    await ServiceClient(settings).insert(
        "consents",
        {
            "user_id": p.user_id if p else None,
            "anon_id": body.anon_id,
            "version": body.version,
            "analytics": analytics,
            "gpc": body.gpc,
        },
    )
    return ConsentOut(recorded=True, analytics=analytics)
