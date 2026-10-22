from __future__ import annotations

import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from sg_api import deps
from sg_api.core import auth
from sg_api.core.config import Settings, get_settings
from sg_api.core.errors import ApiError
from sg_api.main import create_app
from sg_api.services.invites import email_domain_allowed, invite_state

DEPT_A = "10000000-0000-4000-8000-00000000000a"
DEPT_B = "10000000-0000-4000-8000-00000000000b"
ADMIN = "10000000-0000-4000-8000-0000000000aa"
ISSUER = "http://db.invalid:54321/auth/v1"
KEY = ec.generate_private_key(ec.SECP256R1())


class FakeJWKS:
    class _Key:
        key = KEY.public_key()

    def get_signing_key_from_jwt(self, token: str) -> Any:
        return self._Key()


def make_token(sub: str = ADMIN, aal: str = "aal2", **extra: Any) -> str:
    now = int(time.time())
    claims = {
        "sub": sub,
        "aud": "authenticated",
        "iss": ISSUER,
        "exp": now + 900,
        "iat": now,
        "aal": aal,
        "session_id": f"s-{sub}",
        "email": "admin@example.test",
        **extra,
    }
    return jwt.encode(claims, KEY, algorithm="ES256")


class FakeGateway:
    def __init__(self) -> None:
        self.memberships: list[dict[str, Any]] = [
            {"user_id": ADMIN, "department_id": DEPT_A, "role": "dept_admin"}
        ]
        self.domains: list[str] = []
        self.invites: dict[str, dict[str, Any]] = {}
        self.sent: list[str] = []
        self.session_age: int | None = 60
        self.fail_email = False

    async def select(self, token: str, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        if table == "memberships":
            return [m for m in self.memberships if m["user_id"] == params["user_id"][3:]]
        if table == "departments":
            if params["id"][3:] not in (DEPT_A, DEPT_B):
                return []
            return [{"facilities": {"organizations": {"allowed_email_domains": self.domains}}}]
        if table == "invites":
            row = self.invites.get(params["id"][3:])
            return [row] if row else []
        raise AssertionError(table)

    async def insert(self, token: str, table: str, row: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(UTC)
        full = {
            "id": f"00000000-0000-4000-8000-{len(self.invites) + 1:012d}",
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(days=7)).isoformat(),
            "accepted_at": None,
            "revoked_at": None,
            **row,
        }
        self.invites[full["id"]] = full
        return full

    async def update(
        self, token: str, table: str, params: dict[str, str], patch: dict[str, Any]
    ) -> list[dict[str, Any]]:
        row = self.invites.get(params["id"][3:])
        if not row:
            return []
        row.update(patch)
        return [row]

    async def rpc(self, token: str, fn: str, args: dict[str, Any] | None = None) -> Any:
        assert fn == "session_age_seconds"
        return self.session_age

    async def admin_invite(self, email: str, redirect_to: str) -> None:
        if self.fail_email:
            raise ApiError(502, "invite email could not be sent")
        assert redirect_to.endswith("/accept-invite")
        self.sent.append(email)


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
    with TestClient(app) as client:
        yield client


def post(api: TestClient, path: str, token: str | None, body: dict[str, Any] | None = None) -> Any:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return api.post(path, json=body or {}, headers=headers)


def invite_body(
    role: str = "supervisor", dept: str = DEPT_A, email: str = "new@example.com"
) -> dict[str, str]:
    return {"email": email, "department_id": dept, "role": role}


def test_invite_requires_bearer_token(api: TestClient) -> None:
    resp = post(api, "/v1/admin/invites", None, invite_body())
    assert resp.status_code == 401
    assert resp.headers["content-type"].startswith("application/problem+json")


def test_invite_rejects_bad_signature(api: TestClient) -> None:
    other = ec.generate_private_key(ec.SECP256R1())
    claims = {"sub": ADMIN, "aud": "authenticated", "iss": ISSUER, "exp": int(time.time()) + 60}
    bad = jwt.encode(claims, other, algorithm="ES256")
    assert post(api, "/v1/admin/invites", bad, invite_body()).status_code == 401


def test_invite_rejects_expired_token(api: TestClient) -> None:
    token = make_token(exp=int(time.time()) - 10)
    assert post(api, "/v1/admin/invites", token, invite_body()).status_code == 401


def test_invite_requires_aal2(api: TestClient) -> None:
    resp = post(api, "/v1/admin/invites", make_token(aal="aal1"), invite_body())
    assert resp.status_code == 403
    assert "aal2" in resp.json()["detail"]


def test_dept_admin_invites_and_email_is_sent(api: TestClient, gw: FakeGateway) -> None:
    resp = post(api, "/v1/admin/invites", make_token(), invite_body())
    assert resp.status_code == 201, resp.text
    assert resp.json()["role"] == "supervisor"
    assert gw.sent == ["new@example.com"]
    assert next(iter(gw.invites.values()))["invited_by"] == ADMIN


def test_dept_admin_cannot_invite_other_department(api: TestClient) -> None:
    resp = post(api, "/v1/admin/invites", make_token(), invite_body(dept=DEPT_B))
    assert resp.status_code == 403


def test_non_admin_cannot_invite(api: TestClient, gw: FakeGateway) -> None:
    gw.memberships = [{"user_id": ADMIN, "department_id": DEPT_A, "role": "supervisor"}]
    assert post(api, "/v1/admin/invites", make_token(), invite_body()).status_code == 403


def test_platform_admin_rule(api: TestClient, gw: FakeGateway) -> None:
    resp = post(api, "/v1/admin/invites", make_token(), invite_body(role="platform_admin"))
    assert resp.status_code == 403
    gw.memberships.append({"user_id": ADMIN, "department_id": DEPT_B, "role": "platform_admin"})
    resp = post(api, "/v1/admin/invites", make_token(), invite_body(role="platform_admin"))
    assert resp.status_code == 201


def test_domain_restriction(api: TestClient, gw: FakeGateway) -> None:
    gw.domains = ["hospital.org"]
    resp = post(api, "/v1/admin/invites", make_token(), invite_body(email="a@gmail.com"))
    assert resp.status_code == 422
    resp = post(api, "/v1/admin/invites", make_token(), invite_body(email="a@Hospital.org"))
    assert resp.status_code == 201


def test_invalid_email_is_validation_problem(api: TestClient) -> None:
    resp = post(api, "/v1/admin/invites", make_token(), invite_body(email="not-an-email"))
    assert resp.status_code == 422
    assert resp.json()["errors"][0]["loc"][-1] == "email"


def test_failed_email_revokes_invite(api: TestClient, gw: FakeGateway) -> None:
    gw.fail_email = True
    assert post(api, "/v1/admin/invites", make_token(), invite_body()).status_code == 502
    assert next(iter(gw.invites.values()))["revoked_at"] is not None


def test_revoked_invite_cannot_be_resent(api: TestClient) -> None:
    invite_id = post(api, "/v1/admin/invites", make_token(), invite_body()).json()["id"]
    resp = post(api, f"/v1/admin/invites/{invite_id}/revoke", make_token())
    assert resp.status_code == 200 and resp.json()["revoked_at"]
    assert post(api, f"/v1/admin/invites/{invite_id}/resend", make_token()).status_code == 409


def test_resend_extends_expiry_and_resends(api: TestClient, gw: FakeGateway) -> None:
    invite_id = post(api, "/v1/admin/invites", make_token(), invite_body()).json()["id"]
    gw.invites[invite_id]["expires_at"] = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    resp = post(api, f"/v1/admin/invites/{invite_id}/resend", make_token())
    assert resp.status_code == 200
    expires = datetime.fromisoformat(resp.json()["expires_at"])
    assert expires > datetime.now(UTC) + timedelta(days=6)
    assert len(gw.sent) == 2


def test_accepted_invite_cannot_be_revoked(api: TestClient, gw: FakeGateway) -> None:
    invite_id = post(api, "/v1/admin/invites", make_token(), invite_body()).json()["id"]
    gw.invites[invite_id]["accepted_at"] = datetime.now(UTC).isoformat()
    assert post(api, f"/v1/admin/invites/{invite_id}/revoke", make_token()).status_code == 409


def test_unknown_invite_is_404(api: TestClient) -> None:
    path = "/v1/admin/invites/00000000-0000-4000-8000-999999999999/revoke"
    assert post(api, path, make_token()).status_code == 404


@pytest.mark.parametrize(("age", "status"), [(None, 401), (12 * 3600 + 1, 401), (60, 201)])
def test_session_limit_enforced_server_side(
    api: TestClient, gw: FakeGateway, age: int | None, status: int
) -> None:
    gw.session_age = age
    assert post(api, "/v1/admin/invites", make_token(), invite_body()).status_code == status


def test_auth_event_accepts_anonymous_and_logs(
    api: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    resp = post(api, "/v1/audit/auth-event", None, {"event": "sign_in_failure"})
    assert resp.status_code == 202
    lines = [ln for ln in capsys.readouterr().out.splitlines() if "auth_event" in ln]
    assert lines and '"auth_event": "sign_in_failure"' in lines[0] and "@" not in lines[0]


def test_auth_event_rejects_unknown_event(api: TestClient) -> None:
    assert post(api, "/v1/audit/auth-event", None, {"event": "hack"}).status_code == 422


def test_invite_expiry_state() -> None:
    now = datetime(2026, 10, 21, tzinfo=UTC)
    row = {"expires_at": (now + timedelta(days=7)).isoformat()}
    assert invite_state(row, now) == "pending"
    assert invite_state(row, now + timedelta(days=7, seconds=1)) == "expired"
    assert invite_state({**row, "revoked_at": "x"}, now) == "revoked"
    assert invite_state({**row, "accepted_at": "x"}, now) == "accepted"


def test_email_domain_allowed() -> None:
    assert email_domain_allowed("a@x.test", [])
    assert email_domain_allowed("a@X.test", ["x.test"])
    assert not email_domain_allowed("a@y.test", ["x.test"])


def test_recent_totp_window() -> None:
    now = time.time()
    fresh = auth.Principal("u", "t", amr=[{"method": "totp", "timestamp": int(now) - 60}])
    stale = auth.Principal("u", "t", amr=[{"method": "totp", "timestamp": int(now) - 600}])
    password = auth.Principal("u", "t", amr=[{"method": "password", "timestamp": int(now)}])
    auth.check_recent_totp(fresh, now)
    for p in (stale, password):
        with pytest.raises(ApiError):
            auth.check_recent_totp(p, now)
