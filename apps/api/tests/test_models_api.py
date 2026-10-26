"""SG-14: model registry endpoints, internal reload, readiness and the hot swap.
Synthetic ids and a tiny model trained on synthetic rows only."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from sg_api import deps
from sg_api.core import auth, ratelimit, roles
from sg_api.core.config import Settings, get_settings
from sg_api.db.service_client import ServiceClient
from sg_api.main import create_app
from sg_api.services.models import ModelService, build
from sg_ml.features import build_matrix
from sg_ml.testing import feature_row, tiny_artifact_bytes

from .test_security_plans import DEPT, SUP, TECH, FakeGateway, FakeJWKS, auth_h

ADMIN = "30000000-0000-4000-8000-0000000000a9"
INTERNAL = "internal-test-token-0123456789"


class FakeSource:
    def __init__(self) -> None:
        self.active: list[dict[str, Any]] = []
        self.fail = False
        self.downloads = 0

    async def active_versions(self) -> list[dict[str, Any]]:
        if self.fail:
            raise httpx.ConnectError("down")
        return self.active

    async def download(self, path: str) -> bytes:
        self.downloads += 1
        return tiny_artifact_bytes(7 if path.startswith("v1") else 8)

    def set_active(self, version: str) -> None:
        self.active = [
            {
                "version": version,
                "feature_set": "full",
                "artifact_path": f"{version}/artifact.joblib",
            }
        ]


class RegistryGateway(FakeGateway):
    def __init__(self) -> None:
        super().__init__()
        self.memberships.append({"user_id": ADMIN, "department_id": DEPT, "role": "platform_admin"})

    async def select(self, token_: str, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        if table == "model_versions":
            return [
                {
                    "version": "v1",
                    "feature_set": "full",
                    "status": "active",
                    "gates_passed": True,
                    "created_at": "2026-10-26T00:30:00+00:00",
                    "activated_at": "2026-10-26T00:40:00+00:00",
                    "metrics": {"regression": {"hgb_p50": {"mae": 0.8}}},
                }
            ]
        return await super().select(token_, table, params)


@pytest.fixture
def source() -> FakeSource:
    s = FakeSource()
    s.set_active("v1")
    return s


@pytest.fixture
def api(source: FakeSource) -> Iterator[TestClient]:
    settings = Settings(env="test", supabase_url="http://db.invalid:54321", internal_token=INTERNAL)
    app = create_app(settings)
    app.state.model_service = ModelService(source)
    verifier = auth.TokenVerifier(settings, FakeJWKS())  # type: ignore[arg-type]
    gw = RegistryGateway()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[auth.get_verifier] = lambda: verifier
    app.dependency_overrides[deps.get_gateway] = lambda: gw
    deps._session_cache.clear()
    roles.clear_membership_cache()
    ratelimit.reset()
    with TestClient(app) as client:
        yield client


def fresh_totp() -> dict[str, Any]:
    return {"amr": [{"method": "totp", "timestamp": int(time.time()) - 30}]}


def test_startup_loads_the_active_model(api: TestClient) -> None:
    service: ModelService = api.app.state.model_service  # type: ignore[attr-defined]
    assert service.versions() == {"full": "v1"}


def test_list_models_needs_supervisor_or_above(api: TestClient) -> None:
    assert api.get("/v1/models", headers=auth_h(TECH)).status_code == 403
    resp = api.get("/v1/models", headers=auth_h(SUP))
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["version"] == "v1" and body[0]["loaded"] is True


def test_activate_needs_platform_admin_and_fresh_totp(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, Any]] = []

    async def rpc_response(self: ServiceClient, fn: str, args: dict[str, Any]) -> httpx.Response:
        calls.append(args)
        if args["p_version"] == "weak":
            return httpx.Response(400, json={"code": "23514", "message": "gates"})
        if args["p_version"] == "missing":
            return httpx.Response(400, json={"code": "P0002", "message": "nf"})
        return httpx.Response(
            200,
            json={
                "version": args["p_version"],
                "feature_set": "full",
                "status": "active",
                "gates_passed": True,
                "created_at": "2026-10-26T01:00:00+00:00",
                "activated_at": "2026-10-26T01:05:00+00:00",
                "metrics": {},
            },
        )

    monkeypatch.setattr(ServiceClient, "rpc_response", rpc_response)
    assert (
        api.post("/v1/models/v2/activate", headers=auth_h(SUP, **fresh_totp())).status_code == 403
    )
    stale = api.post("/v1/models/v2/activate", headers=auth_h(ADMIN))
    assert stale.status_code == 401 and "reauth" in stale.json()["type"]
    weak = api.post("/v1/models/weak/activate", headers=auth_h(ADMIN, **fresh_totp()))
    assert weak.status_code == 409 and weak.json()["type"].endswith("gates-not-passed")
    missing = api.post("/v1/models/missing/activate", headers=auth_h(ADMIN, **fresh_totp()))
    assert missing.status_code == 404
    ok = api.post("/v1/models/v2/activate", headers=auth_h(ADMIN, **fresh_totp()))
    assert ok.status_code == 200 and ok.json()["status"] == "active"
    assert calls[-1] == {"p_version": "v2", "p_actor": ADMIN}


def test_internal_reload_requires_the_token(api: TestClient, source: FakeSource) -> None:
    assert api.post("/v1/internal/models/reload").status_code == 404
    bad = api.post("/v1/internal/models/reload", headers={"X-Internal-Token": "nope"})
    assert bad.status_code == 404
    source.set_active("v2")
    resp = api.post("/v1/internal/models/reload", headers={"X-Internal-Token": INTERNAL})
    assert resp.status_code == 200
    assert resp.json() == {"changed": True, "versions": {"full": "v2"}}


def test_ready_reports_model_versions(api: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from sg_api.routers import health

    async def ok(_: Settings) -> health.Check:
        return health.Check(ok=True)

    monkeypatch.setattr(health, "check_database", ok)
    resp = api.get("/ready")
    assert resp.status_code == 200
    assert resp.json()["models"] == {"full": "v1"}


async def test_refresh_keeps_current_model_when_nothing_changed_or_source_fails() -> None:
    source = FakeSource()
    source.set_active("v1")
    service = ModelService(source)
    assert await service.refresh() is True
    first = service.get()
    assert await service.refresh() is False and service.get() is first
    assert source.downloads == 1
    source.fail = True
    assert await service.refresh() is False
    assert service.get() is first and service.last_error == "ConnectError"


def test_swap_under_concurrent_requests() -> None:
    """Predictions keep flowing while the model is swapped back and forth: no errors, and every
    answer comes from one of the two complete models (never a half-built one)."""
    a = build("v1", "full", tiny_artifact_bytes(7))
    b = build("v2", "full", tiny_artifact_bytes(8))
    X = build_matrix(_frame(), a.feature_list)
    expected = {a.predict(X).p50, b.predict(X).p50}
    assert len(expected) == 2
    service = ModelService(source=None)
    service.swap({"full": a})
    errors: list[BaseException] = []
    seen: set[float] = set()
    stop = threading.Event()

    def reader() -> None:
        while not stop.is_set():
            try:
                model = service.get()
                assert model is not None
                seen.add(model.predict(X).p50)
            except BaseException as exc:  # collected and asserted below
                errors.append(exc)

    threads = [threading.Thread(target=reader) for _ in range(4)]
    for t in threads:
        t.start()
    for i in range(40):
        service.swap({"full": b if i % 2 == 0 else a})
        time.sleep(0.005)
    stop.set()
    for t in threads:
        t.join()
    assert not errors
    assert seen <= expected and seen


def _frame() -> Any:
    import pandas as pd

    return pd.DataFrame([feature_row(7)])
