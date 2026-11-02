"""SG-22: contract fuzzing with Schemathesis against the real FastAPI app (in process, ASGI).

Every operation in the generated OpenAPI schema gets fuzzed requests from a signed aal2 token
(the same local test JWKS as the SG-11 tests) for a department admin who is also a supervisor.
Checks: no 5xx, and every response matches its documented status, content type and schema.
The database is an in-memory gateway, so most writes end in documented 404/409/422 problems,
which is exactly what the contract must describe.

Examples per operation: SG_FUZZ_EXAMPLES (default 15 in test-py; the contract CI job uses more).
"""

from __future__ import annotations

import datetime as dt
import os
import uuid
from typing import Any

import pytest
import schemathesis
from hypothesis import HealthCheck, settings
from hypothesis import strategies as st

from sg_api import deps
from sg_api.core import auth, ratelimit, roles
from sg_api.core.config import Settings, get_settings
from sg_api.main import create_app
from sg_api.services.models import ModelService, build
from sg_ml.testing import tiny_artifact_bytes

from .test_security_plans import DEPT, SUP, FakeJWKS, auth_h

EXAMPLES = int(os.environ.get("SG_FUZZ_EXAMPLES", "15"))


class FuzzGateway:
    """Accepts anything: selects return no rows (except the caller's memberships and the
    department), writes echo the row back. Enough to reach every branch's error handling."""

    async def select(self, token: str, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        if table == "memberships":
            return [
                {"user_id": SUP, "department_id": DEPT, "role": "supervisor"},
                {"user_id": SUP, "department_id": DEPT, "role": "dept_admin"},
            ]
        if table == "departments":
            return [{"settings": {}, "facilities": {"timezone": "America/New_York"}}]
        return []

    async def insert(self, token: str, table: str, row: dict[str, Any]) -> dict[str, Any]:
        now = dt.datetime.now(dt.UTC).isoformat()
        return {"id": str(uuid.uuid4()), "created_at": now, "updated_at": now, **row}

    async def insert_many(
        self, token: str, table: str, rows: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        return rows

    async def update(
        self, token: str, table: str, params: dict[str, str], patch: dict[str, Any]
    ) -> list[dict[str, Any]]:
        return []

    async def upsert(
        self, token: str, table: str, row: dict[str, Any], on_conflict: str
    ) -> dict[str, Any]:
        return {"updated_at": dt.datetime.now(dt.UTC).isoformat(), **row}

    async def rpc(self, token: str, fn: str, args: dict[str, Any] | None = None) -> Any:
        return 60

    async def admin_invite(self, email: str, redirect_to: str) -> None:
        return None


def make_app() -> Any:
    cfg = Settings(env="test", supabase_url="http://db.invalid:54321")
    app = create_app(cfg)
    service = ModelService(source=None)
    service.swap({"full": build("v-fuzz", "full", tiny_artifact_bytes(7))})
    app.state.model_service = service
    verifier = auth.TokenVerifier(cfg, FakeJWKS())  # type: ignore[arg-type]
    gw = FuzzGateway()
    app.dependency_overrides[get_settings] = lambda: cfg
    app.dependency_overrides[auth.get_verifier] = lambda: verifier
    app.dependency_overrides[deps.get_gateway] = lambda: gw
    return app


APP = make_app()
# Generated emails use reserved TLDs (.test, .invalid) that the API's email validator rightly
# refuses; real addresses have ordinary domains.
schemathesis.openapi.format(
    "email",
    st.from_regex(r"\A[a-z][a-z0-9]{0,12}(\.[a-z0-9]{1,8})?@sterileguard\.dev\Z", fullmatch=True),
)
# /ready is a health probe: it answers 503 by design while the database is unreachable.
schema = schemathesis.openapi.from_asgi("/openapi.json", APP).exclude(path="/ready")


@pytest.fixture(autouse=True)
def _fresh_state() -> None:
    deps._session_cache.clear()
    roles.clear_membership_cache()
    ratelimit.reset()


@schema.parametrize()
@settings(
    max_examples=EXAMPLES,
    deadline=None,
    suppress_health_check=list(HealthCheck),
    derandomize=True,
)
def test_api_contract(case: schemathesis.Case) -> None:
    case.call_and_validate(headers=auth_h(SUP))
