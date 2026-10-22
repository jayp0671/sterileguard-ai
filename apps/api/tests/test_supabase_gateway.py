from __future__ import annotations

import json

import httpx
import pytest

from sg_api.core.config import Settings
from sg_api.core.errors import ApiError
from sg_api.services.supabase import SupabaseGateway


def gateway(handler: httpx.MockTransport, service_key: str | None = "svc") -> SupabaseGateway:
    settings = Settings(
        env="test",
        supabase_url="http://sb.test",
        supabase_anon_key="anon",
        supabase_service_role_key=service_key,
    )
    return SupabaseGateway(settings, httpx.AsyncClient(transport=handler))


async def test_select_forwards_user_token_for_rls() -> None:
    seen: dict[str, str] = {}

    def handle(req: httpx.Request) -> httpx.Response:
        seen.update(
            auth=req.headers["Authorization"], apikey=req.headers["apikey"], url=str(req.url)
        )
        return httpx.Response(200, json=[{"id": 1}])

    rows = await gateway(httpx.MockTransport(handle)).select("user-tok", "invites", {"id": "eq.1"})
    assert rows == [{"id": 1}]
    assert seen["auth"] == "Bearer user-tok" and seen["apikey"] == "anon"
    assert seen["url"] == "http://sb.test/rest/v1/invites?id=eq.1"


async def test_insert_and_update_return_representation() -> None:
    def handle(req: httpx.Request) -> httpx.Response:
        assert req.headers["Prefer"] == "return=representation"
        return httpx.Response(201, json=[json.loads(req.content)])

    gw = gateway(httpx.MockTransport(handle))
    assert await gw.insert("t", "invites", {"a": 1}) == {"a": 1}
    assert await gw.update("t", "invites", {"id": "eq.1"}, {"b": 2}) == [{"b": 2}]


async def test_rpc_posts_to_rpc_endpoint() -> None:
    def handle(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/rest/v1/rpc/session_age_seconds"
        return httpx.Response(200, json=42)

    assert await gateway(httpx.MockTransport(handle)).rpc("t", "session_age_seconds") == 42


@pytest.mark.parametrize(
    ("status", "mapped"), [(401, 403), (403, 403), (409, 409), (400, 422), (500, 502)]
)
async def test_errors_map_to_problem_status(status: int, mapped: int) -> None:
    gw = gateway(httpx.MockTransport(lambda _: httpx.Response(status, json={})))
    with pytest.raises(ApiError) as exc:
        await gw.select("t", "invites", {})
    assert exc.value.status == mapped


async def test_admin_invite_uses_service_role_and_redirect() -> None:
    seen: dict[str, str] = {}

    def handle(req: httpx.Request) -> httpx.Response:
        seen.update(auth=req.headers["Authorization"], url=str(req.url), body=req.content.decode())
        return httpx.Response(200, json={})

    await gateway(httpx.MockTransport(handle)).admin_invite(
        "a@example.com", "http://w/accept-invite"
    )
    assert seen["auth"] == "Bearer svc"
    assert seen["url"].startswith("http://sb.test/auth/v1/invite?redirect_to=")
    assert json.loads(seen["body"]) == {"email": "a@example.com"}


async def test_admin_invite_errors() -> None:
    with pytest.raises(ApiError) as missing:
        await gateway(httpx.MockTransport(lambda _: httpx.Response(200)), None).admin_invite(
            "a", "r"
        )
    assert missing.value.status == 503
    for status, mapped in ((422, 409), (500, 502)):
        gw = gateway(httpx.MockTransport(lambda _, s=status: httpx.Response(s, json={})))
        with pytest.raises(ApiError) as exc:
            await gw.admin_invite("a@example.com", "r")
        assert exc.value.status == mapped
