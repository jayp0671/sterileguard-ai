"""Shared FastAPI dependencies. SG-11 extends these with role checks and idempotency keys."""

from __future__ import annotations

import time

from fastapi import Depends

from sg_api.core.auth import Principal, check_session_age, require_aal2
from sg_api.core.config import Settings, get_settings
from sg_api.services.invites import InviteService
from sg_api.services.supabase import Gateway, SupabaseGateway

_gateway: SupabaseGateway | None = None
# session_id -> (checked_at, age_at_check); avoids one RPC per request (60 s cache).
_session_cache: dict[str, tuple[float, int | None]] = {}
SESSION_CACHE_S = 60.0


def get_gateway(settings: Settings = Depends(get_settings)) -> Gateway:
    global _gateway
    if _gateway is None or _gateway.settings is not settings:
        _gateway = SupabaseGateway(settings)
    return _gateway


async def session_age(principal: Principal, gw: Gateway) -> int | None:
    key = principal.session_id or principal.user_id
    now = time.monotonic()
    cached = _session_cache.get(key)
    if cached and now - cached[0] < SESSION_CACHE_S:
        age = cached[1]
        return None if age is None else age + int(now - cached[0])
    result = await gw.rpc(principal.token, "session_age_seconds")
    age = None if result is None else int(result)
    _session_cache[key] = (now, age)
    return age


async def current_user(
    principal: Principal = Depends(require_aal2), gw: Gateway = Depends(get_gateway)
) -> Principal:
    """aal2 caller whose session still exists and is younger than 12 hours."""
    check_session_age(await session_age(principal, gw))
    return principal


def get_invite_service(
    gw: Gateway = Depends(get_gateway), settings: Settings = Depends(get_settings)
) -> InviteService:
    return InviteService(gw, settings.site_url)
