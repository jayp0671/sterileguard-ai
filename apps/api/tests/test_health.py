from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

import httpx
import pytest
from fastapi import Query
from fastapi.testclient import TestClient

from sg_api.core.config import Settings
from sg_api.routers import health


def test_health_returns_ok_and_version(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "version": "abcdef123456"}


def test_ready_returns_503_with_reason_when_db_down(client: TestClient) -> None:
    resp = client.get("/ready")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["database"]["ok"] is False
    assert "database unreachable" in body["checks"]["database"]["reason"]
    assert "model" in body["checks"]


def test_ready_returns_200_when_db_and_model_ok(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def ok(_: Settings) -> health.Check:
        return health.Check(ok=True)

    monkeypatch.setattr(health, "check_database", ok)
    from sg_api.services.models import ModelService

    service = ModelService(source=None)
    service.swap({"full": SimpleNamespace(version="v-test")})  # type: ignore[dict-item]
    client.app.state.model_service = service  # type: ignore[attr-defined]
    resp = client.get("/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


async def test_check_database_reports_5xx(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(503))
    real = httpx.AsyncClient

    def fake(**kw: object) -> httpx.AsyncClient:
        return real(transport=transport)

    monkeypatch.setattr(health.httpx, "AsyncClient", fake)
    check = await health.check_database(settings)
    assert check.ok is False and check.reason == "database returned 503"


def test_request_id_is_propagated(client: TestClient) -> None:
    resp = client.get("/health", headers={"X-Request-ID": "abc-123"})
    assert resp.headers["X-Request-ID"] == "abc-123"


def test_request_id_generated_when_missing_or_unsafe(client: TestClient) -> None:
    resp = client.get("/health", headers={"X-Request-ID": "bad id with spaces"})
    uuid.UUID(resp.headers["X-Request-ID"])


def test_not_found_is_problem_json(client: TestClient) -> None:
    resp = client.get("/nope", headers={"X-Request-ID": "rid-1"})
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/problem+json")
    body = resp.json()
    assert body["status"] == 404 and body["title"] == "Not Found" and body["request_id"] == "rid-1"


def test_validation_error_is_problem_json_with_field_errors(client: TestClient) -> None:
    @client.app.get("/_probe")  # type: ignore[attr-defined]
    def probe(n: int = Query()) -> dict[str, int]:
        return {"n": n}

    resp = client.get("/_probe", params={"n": "x"}, headers={"X-Request-ID": "rid-2"})
    assert resp.status_code == 422
    body = resp.json()
    assert body["request_id"] == "rid-2"
    assert body["errors"][0]["loc"] == ["query", "n"]


def test_logs_are_json_with_request_id(
    client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    client.get("/health", headers={"X-Request-ID": "rid-log"})
    lines = [
        json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")
    ]
    assert any(e.get("request_id") == "rid-log" and e.get("event") == "request" for e in lines)


def test_openapi_spec_is_deterministic() -> None:
    from sg_api.openapi import spec

    assert spec() == spec()
    assert '"Problem"' in spec()


def test_cors_allows_vercel_previews_by_pattern() -> None:
    from fastapi.testclient import TestClient as Client

    from sg_api.main import create_app

    settings = Settings(
        env="test",
        supabase_url="http://db.invalid:54321",
        cors_origins=["https://sterileguard-staging.vercel.app"],
        cors_origin_regex=r"^https://sterileguard-ai-[a-z0-9-]+-team\.vercel\.app$",
    )
    with Client(create_app(settings)) as c:

        def allowed(origin: str) -> str | None:
            return c.get("/health", headers={"Origin": origin}).headers.get(
                "access-control-allow-origin"
            )

        assert allowed("https://sterileguard-staging.vercel.app")
        assert allowed("https://sterileguard-ai-git-sg-16-team.vercel.app")
        assert allowed("https://evil.example.com") is None
