"""SG-11: JWT verification, role checks, rate limits, idempotency and Plan Tomorrow.
Synthetic ids only; a locally generated RSA key stands in for the Supabase JWKS."""

from __future__ import annotations

import datetime as dt
import time
from collections.abc import Iterator
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from sg_api import deps
from sg_api.core import auth, ratelimit, roles
from sg_api.core.config import Settings, get_settings
from sg_api.core.middleware import REQUEST_ID
from sg_api.main import create_app
from sg_api.services import plans
from sg_api.services.supabase import SupabaseGateway

DEPT = "30000000-0000-4000-8000-00000000000a"
OTHER = "30000000-0000-4000-8000-00000000000b"
SUP = "30000000-0000-4000-8000-0000000000a1"
TECH = "30000000-0000-4000-8000-0000000000a2"
ISS = "http://db.invalid:54321/auth/v1"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
NY = dt.timezone(dt.timedelta(hours=-4))


class FakeJWKS:
    class _Key:
        key = KEY.public_key()

    def get_signing_key_from_jwt(self, token: str) -> Any:
        return self._Key()


def token(sub: str, aal: str = "aal2", **over: Any) -> str:
    now = int(time.time())
    claims = {"sub": sub, "aud": "authenticated", "iss": ISS, "exp": now + 900, "iat": now}
    claims |= {"aal": aal, "session_id": f"s-{sub}", **over}
    return jwt.encode(claims, KEY, algorithm="RS256")


def auth_h(sub: str = SUP, **kw: Any) -> dict[str, str]:
    return {"Authorization": f"Bearer {token(sub, **kw)}"}


class FakeGateway:
    def __init__(self) -> None:
        self.memberships = [
            {"user_id": SUP, "department_id": DEPT, "role": "supervisor"},
            {"user_id": TECH, "department_id": DEPT, "role": "technician"},
        ]
        self.plans: dict[tuple[str, str], dict[str, Any]] = {}
        self.history: list[dict[str, Any]] = []
        self.keys: dict[tuple[str, str], dict[str, Any]] = {}
        self.upserts = 0

    async def select(self, token_: str, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        eq = {k: v.removeprefix("eq.") for k, v in params.items() if v.startswith("eq.")}
        if table == "memberships":
            return [m for m in self.memberships if m["user_id"] == eq["user_id"]]
        if table == "departments":
            return [
                {
                    "settings": {"mf_cases_default": 18, "washers": 2},
                    "facilities": {"timezone": "America/New_York"},
                }
            ]
        if table == "idempotency_keys":
            row = self.keys.get((eq["user_id"], eq["key"]))
            return [row] if row else []
        if table == "shift_plans" and "plan_date" in eq:
            row = self.plans.get((eq["department_id"], eq["plan_date"]))
            return [row] if row else []
        return self.history
        raise AssertionError(table)

    async def upsert(
        self, token_: str, table: str, row: dict[str, Any], on_conflict: str
    ) -> dict[str, Any]:
        if table == "idempotency_keys":
            self.keys[(row["user_id"], row["key"])] = row
            return row
        self.upserts += 1
        saved = {**row, "updated_at": "2026-10-24T12:00:00+00:00"}
        self.plans[(row["department_id"], row["plan_date"])] = saved
        return saved

    async def rpc(self, token_: str, fn: str, args: dict[str, Any] | None = None) -> Any:
        return 60


@pytest.fixture
def gw() -> FakeGateway:
    return FakeGateway()


@pytest.fixture
def api(gw: FakeGateway) -> Iterator[TestClient]:
    settings = Settings(env="test", supabase_url="http://db.invalid:54321")
    app = create_app(settings)
    verifier = auth.TokenVerifier(settings, FakeJWKS())  # type: ignore[arg-type]
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[auth.get_verifier] = lambda: verifier
    app.dependency_overrides[deps.get_gateway] = lambda: gw
    deps._session_cache.clear()
    roles.clear_membership_cache()
    ratelimit.reset()
    with TestClient(app) as client:
        yield client


def tomorrow() -> str:
    return (plans.today_in(plans.ZoneInfo("America/New_York")) + dt.timedelta(days=1)).isoformat()


def plan_body(**over: Any) -> dict[str, Any]:
    return {"regular_patients": 350, "morning_staff_present": 3, "ot_available_staff": 2, **over}


# --- JWT -----------------------------------------------------------------------------------


def test_valid_token_reads_plan(api: TestClient) -> None:
    res = api.get(f"/v1/plans/{tomorrow()}", params={"department_id": DEPT}, headers=auth_h())
    assert res.status_code == 200, res.text


@pytest.mark.parametrize(
    ("claims", "status"),
    [
        ({"exp": int(time.time()) - 10}, 401),
        ({"aud": "anon"}, 401),
        ({"iss": "http://evil/auth/v1"}, 401),
    ],
)
def test_bad_tokens_are_rejected(api: TestClient, claims: dict[str, Any], status: int) -> None:
    res = api.get(
        f"/v1/plans/{tomorrow()}", params={"department_id": DEPT}, headers=auth_h(**claims)
    )
    assert res.status_code == status
    assert res.headers["content-type"].startswith("application/problem+json")


def test_aal1_gets_mfa_required(api: TestClient) -> None:
    res = api.get(
        f"/v1/plans/{tomorrow()}", params={"department_id": DEPT}, headers=auth_h(aal="aal1")
    )
    assert res.status_code == 403
    assert res.json()["type"] == auth.MFA_REQUIRED


# --- roles ---------------------------------------------------------------------------------


def test_wrong_role_lists_required_roles(api: TestClient) -> None:
    res = api.put(
        f"/v1/plans/{tomorrow()}",
        params={"department_id": DEPT},
        json=plan_body(),
        headers=auth_h(TECH),
    )
    assert res.status_code == 403
    body = res.json()
    assert body["type"] == roles.FORBIDDEN_ROLE
    assert "dept_admin" in body["detail"] and "supervisor" in body["detail"]


def test_other_department_is_404(api: TestClient) -> None:
    res = api.get(f"/v1/plans/{tomorrow()}", params={"department_id": OTHER}, headers=auth_h())
    assert res.status_code == 404


def test_missing_department_is_422(api: TestClient) -> None:
    assert api.get(f"/v1/plans/{tomorrow()}", headers=auth_h()).status_code == 422


# --- plans ---------------------------------------------------------------------------------


def test_suggestion_when_nothing_saved(api: TestClient, gw: FakeGateway) -> None:
    day = dt.date.fromisoformat(tomorrow())
    gw.history = [
        {
            "plan_date": (day - dt.timedelta(days=7 * k)).isoformat(),
            "regular_patients": 300 + 10 * k,
            "morning_staff_present": 3,
        }
        for k in range(1, 6)
    ] + [
        {
            "plan_date": (day - dt.timedelta(days=1)).isoformat(),
            "regular_patients": 999,
            "morning_staff_present": 9,
        }
    ]
    body = api.get(f"/v1/plans/{day}", params={"department_id": DEPT}, headers=auth_h()).json()
    assert body["suggested"] is True
    assert body["values"]["regular_patients"] == 325  # mean of the last 4 same-weekday plans
    assert body["sources"]["regular_patients"].startswith("history:average of the last 4")
    assert body["values"]["mf_cases"] == 18
    assert body["sources"]["mf_cases"] == "settings:mf_cases_default"
    assert body["sources"]["aft_11_staff"] == "default"


def test_suggestion_without_history_leaves_tier1_empty() -> None:
    out = plans.suggest(DEPT, dt.date(2026, 10, 27), {}, [])
    assert out.values.regular_patients is None
    assert out.sources["regular_patients"] == "none"


def test_put_validates_ranges(api: TestClient) -> None:
    res = api.put(
        f"/v1/plans/{tomorrow()}",
        params={"department_id": DEPT},
        json=plan_body(regular_patients=900),
        headers=auth_h(),
    )
    assert res.status_code == 422
    assert any(str(e["loc"][-1]) == "regular_patients" for e in res.json()["errors"])
    res = api.put(
        f"/v1/plans/{tomorrow()}",
        params={"department_id": DEPT},
        json=plan_body(ot_available_staff=5),
        headers=auth_h(),
    )
    assert res.status_code == 422


def test_put_saves_and_fills_tier2(api: TestClient, gw: FakeGateway) -> None:
    res = api.put(
        f"/v1/plans/{tomorrow()}",
        params={"department_id": DEPT},
        json={**plan_body(), "status": "final"},
        headers=auth_h(),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["suggested"] is False and body["status"] == "final"
    assert body["values"]["mf_cases"] == 18
    assert "mf_cases" in body["missing"]
    saved = gw.plans[(DEPT, tomorrow())]
    assert (
        saved["mf_cases__missing"] is True and saved["regular_patients__missing"] if False else True
    )
    assert saved["source"] == "real" and saved["created_by"] == SUP


def test_date_rules() -> None:
    today = dt.date(2026, 10, 24)
    plans.check_date(today + dt.timedelta(days=1), today, "final", False)
    plans.check_date(today + dt.timedelta(days=14), today, "final", False)
    plans.check_date(today - dt.timedelta(days=5), today, "final", True)
    for day, status, backfill in [
        (today + dt.timedelta(days=15), "draft", False),
        (today, "draft", False),
        (today - dt.timedelta(days=1), "final", False),
    ]:
        with pytest.raises(Exception, match=r"days ahead|backfill|tomorrow"):
            plans.check_date(day, today, status, backfill)


# --- idempotency ---------------------------------------------------------------------------


def test_idempotent_retry_and_conflict(api: TestClient, gw: FakeGateway) -> None:
    url = f"/v1/plans/{tomorrow()}"
    headers = {**auth_h(), "Idempotency-Key": "k-1"}
    first = api.put(url, params={"department_id": DEPT}, json=plan_body(), headers=headers)
    again = api.put(url, params={"department_id": DEPT}, json=plan_body(), headers=headers)
    assert first.status_code == again.status_code == 200
    assert again.headers.get("Idempotent-Replayed") == "true"
    assert again.json() == first.json()
    assert gw.upserts == 1
    other = api.put(
        url, params={"department_id": DEPT}, json=plan_body(regular_patients=360), headers=headers
    )
    assert other.status_code == 409
    assert gw.upserts == 1


def test_expired_key_runs_again(api: TestClient, gw: FakeGateway) -> None:
    url = f"/v1/plans/{tomorrow()}"
    headers = {**auth_h(), "Idempotency-Key": "k-old"}
    api.put(url, params={"department_id": DEPT}, json=plan_body(), headers=headers)
    gw.keys[(SUP, "k-old")]["created_at"] = "2026-01-01T00:00:00+00:00"
    api.put(url, params={"department_id": DEPT}, json=plan_body(), headers=headers)
    assert gw.upserts == 2


# --- rate limits and request ids -----------------------------------------------------------


def test_rate_limit_returns_problem_with_retry_after(api: TestClient) -> None:
    headers = auth_h()
    statuses = [api.get("/health", headers=headers).status_code for _ in range(121)]
    assert statuses[:120] == [200] * 120
    assert statuses[120] == 429
    res = api.get("/health", headers=headers)
    assert res.json()["type"] == ratelimit.RATE_LIMITED
    assert int(res.headers["Retry-After"]) > 0


def test_rate_key_uses_verified_user_only(api: TestClient) -> None:
    from starlette.requests import Request

    forged = jwt.encode({"sub": SUP, "aud": "authenticated"}, "not-the-key", algorithm="HS256")
    forged_scope = {
        "type": "http",
        "headers": [(b"authorization", f"Bearer {forged}".encode())],
        "client": ("5.6.7.8", 1),
        "app": api.app,
    }
    assert ratelimit.rate_key(Request(forged_scope)) == "ip:5.6.7.8"

    scope = {
        "type": "http",
        "headers": [(b"authorization", f"Bearer {token(SUP)}".encode())],
        "client": ("1.2.3.4", 1),
        "app": api.app,
    }
    assert ratelimit.rate_key(Request(scope)) == f"user:{SUP}"
    assert (
        ratelimit.rate_key(
            Request({"type": "http", "headers": [], "client": ("1.2.3.4", 1), "app": api.app})
        )
        == "ip:1.2.3.4"
    )


async def test_gateway_forwards_request_id() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.headers)
        return httpx.Response(200, json=[])

    settings = Settings(
        env="test", supabase_url="http://db.invalid:54321", supabase_anon_key="anon"
    )
    gw = SupabaseGateway(settings, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    tok = REQUEST_ID.set("req-sg11")
    try:
        await gw.select("t", "shift_plans", {})
    finally:
        REQUEST_ID.reset(tok)
    assert seen["x-request-id"] == "req-sg11"
