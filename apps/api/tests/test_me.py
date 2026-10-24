from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from sg_api import deps
from sg_api.core import auth
from sg_api.core.config import Settings, get_settings
from sg_api.main import create_app

USER = "10000000-0000-4000-8000-0000000000aa"
KEY = ec.generate_private_key(ec.SECP256R1())


class FakeJWKS:
    class _Key:
        key = KEY.public_key()

    def get_signing_key_from_jwt(self, token: str) -> Any:
        return self._Key()


def make_token(sub: str, aal: str = "aal2") -> str:
    now = int(time.time())
    claims = {
        "sub": sub,
        "aud": "authenticated",
        "iss": "http://db.invalid:54321/auth/v1",
        "exp": now + 900,
        "iat": now,
        "aal": aal,
        "session_id": f"s-{sub}",
    }
    return jwt.encode(claims, KEY, algorithm="ES256")


class MeGateway:
    async def select(self, token: str, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        if table == "profiles":
            return [{"display_name": None, "locale": "en", "theme": "dark"}]
        return [
            {"department_id": "d2", "role": "technician", "departments": {"name": "Zeta"}},
            {"department_id": "d1", "role": "supervisor", "departments": {"name": "Dental CS"}},
            {"department_id": "d1", "role": "dept_admin", "departments": {"name": "Dental CS"}},
        ]

    async def rpc(self, token: str, fn: str, args: dict[str, Any] | None = None) -> Any:
        return 60


@pytest.fixture
def api() -> Iterator[TestClient]:
    settings = Settings(env="test", supabase_url="http://db.invalid:54321")
    app = create_app(settings)
    verifier = auth.TokenVerifier(settings, FakeJWKS())  # type: ignore[arg-type]
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[auth.get_verifier] = lambda: verifier
    app.dependency_overrides[deps.get_gateway] = lambda: MeGateway()
    deps._session_cache.clear()
    with TestClient(app) as client:
        yield client


def test_me_groups_roles_by_department(api: TestClient) -> None:
    res = api.get("/v1/me", headers={"Authorization": f"Bearer {make_token(USER)}"})
    assert res.status_code == 200
    body = res.json()
    assert body["id"] == USER and body["aal"] == "aal2" and body["theme"] == "dark"
    assert [m["department_name"] for m in body["memberships"]] == ["Dental CS", "Zeta"]
    assert sorted(body["memberships"][0]["roles"]) == ["dept_admin", "supervisor"]


def test_me_requires_aal2(api: TestClient) -> None:
    res = api.get("/v1/me", headers={"Authorization": f"Bearer {make_token(USER, aal='aal1')}"})
    assert res.status_code == 403
    assert api.get("/v1/me").status_code == 401
