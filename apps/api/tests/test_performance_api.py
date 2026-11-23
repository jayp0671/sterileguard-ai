"""SG-24 Part B: model performance. Synthetic forecasts and actuals only."""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi.testclient import TestClient

from sg_api import deps
from sg_api.core import auth, ratelimit, roles
from sg_api.core.config import Settings, get_settings
from sg_api.db import service_client
from sg_api.main import create_app
from sg_api.services import performance as perf
from sg_api.services import plans as plan_svc

from .test_security_plans import DEPT, SUP, TECH, FakeGateway, FakeJWKS, auth_h

PLATFORM = "30000000-0000-4000-8000-0000000000c1"
THRESH = {"source": "simulated_provisional", "low_max": 5.67, "moderate_max": 12.13}
CARD = {
    "metrics": {
        "feature_sets": {
            "full": {"mae": 0.82, "rmse": 1.96, "coverage_80": 0.812, "mean_width_80": 2.67},
            "core": {"mae": 6.8, "rmse": 8.06, "coverage_80": 0.903, "mean_width_80": 21.66},
        },
        "regression": {"baseline_ridge": {"mae": 1.91}, "hgb_p50": {"mae": 0.82}},
    },
    "datasets": ["a76064e0-0000-4000-8000-000000000000"],
    "thresholds": [5.67, 12.13],
    "thresholds_source": "simulated_provisional",
    "shap_global_top10": [{"feature": "ot_available_staff", "mean_abs_shap": 6.2}],
    "intended_use": "Decision support only. Model estimate, not a guarantee.",
    "limitations": ["Trained on simulated days."],
    "features": ["regular_patients"],
    "gates": [{"name": "interval_coverage", "passed": True, "required": True, "message": "ok"}],
}


def fc(
    day: str, p50: float, created: str = "2026-11-01T20:00:00+00:00", **kw: Any
) -> dict[str, Any]:
    return {
        "target_date": day,
        "ot_p10": p50 - 1,
        "ot_p50": p50,
        "ot_p90": p50 + 1,
        "burden_class": kw.get("cls", "moderate"),
        "thresholds": kw.get("thresholds", THRESH),
        "created_at": created,
    }


def act(day: str, hours: float, source: str = "real") -> dict[str, Any]:
    return {"shift_date": day, "ot_labor_hours": hours, "source": source, "status": "approved"}


def test_live_metrics_join_latest_forecast_with_real_actuals() -> None:
    forecasts = [
        fc("2026-11-02", 4.0, "2026-11-01T10:00:00+00:00"),
        fc("2026-11-02", 6.0, "2026-11-01T22:00:00+00:00"),  # latest wins
        fc("2026-11-03", 8.0),
        fc("2026-11-04", 3.0),
    ]
    actuals = [act("2026-11-02", 6.5), act("2026-11-03", 10.0), act("2026-11-04", 2.0, "simulated")]
    out = perf.live_metrics(forecasts, actuals, 30)
    assert out["days"] == 2  # the simulated day never counts as real accuracy
    assert out["mae"] == pytest.approx((0.5 + 2.0) / 2)
    assert out["bias"] == pytest.approx((0.5 + 2.0) / 2)
    assert out["rmse"] == pytest.approx(((0.25 + 4) / 2) ** 0.5, abs=1e-3)
    assert out["coverage_80"] == 0.5  # 6.5 in [5, 7]; 10 outside [7, 9]
    assert sum(b["count"] for b in out["residual_histogram"]) == 2
    assert out["confusion"] is None  # provisional thresholds: no confusion matrix


def test_confusion_matrix_only_with_real_thresholds() -> None:
    real = {"source": "real", "low_max": 4.0, "moderate_max": 9.0}
    forecasts = [
        fc("2026-11-02", 3.0, cls="low", thresholds=real),
        fc("2026-11-03", 8.0, thresholds=real),
    ]
    out = perf.live_metrics(forecasts, [act("2026-11-02", 3.5), act("2026-11-03", 12.0)], 30)
    assert out["confusion"]["labels"] == ["low", "moderate", "high"]
    assert out["confusion"]["matrix"] == [[1, 0, 0], [0, 0, 0], [0, 1, 0]]


def test_empty_live_metrics() -> None:
    out = perf.live_metrics([fc("2026-11-02", 3.0)], [], 30)
    assert out["days"] == 0 and out["mae"] is None and out["daily"] == []


class PerfGateway(FakeGateway):
    def __init__(self) -> None:
        super().__init__()
        self.memberships.append(
            {"user_id": PLATFORM, "department_id": DEPT, "role": "platform_admin"}
        )
        today = plan_svc.today_in(ZoneInfo("America/New_York"))
        self.day = today.isoformat()
        self.forecasts = [fc(self.day, 5.0)]
        self.actuals = [act(self.day, 5.5)]

    async def select(self, token_: str, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        if table == "model_versions":
            base = {
                "feature_set": "full",
                "gates_passed": True,
                "metrics": CARD["metrics"],
                "card": CARD,
            }
            return [
                {
                    **base,
                    "version": "v2",
                    "status": "active",
                    "created_at": "2026-10-26T00:00:00+00:00",
                    "activated_at": "2026-10-26T01:00:00+00:00",
                    "activated_by": None,
                },
                {
                    **base,
                    "version": "v1",
                    "status": "retired",
                    "created_at": "2026-10-25T00:00:00+00:00",
                    "activated_at": "2026-10-25T01:00:00+00:00",
                    "activated_by": PLATFORM,
                },
            ]
        if table == "forecasts":
            return self.forecasts
        if table == "shift_actuals":
            assert params["source"] == "eq.real" and params["status"] == "eq.approved"
            return self.actuals
        return await super().select(token_, table, params)


@pytest.fixture
def pgw() -> PerfGateway:
    return PerfGateway()


@pytest.fixture
def api(pgw: PerfGateway) -> Iterator[TestClient]:
    settings = Settings(env="test", supabase_url="http://db.invalid:54321")
    app = create_app(settings)
    verifier = auth.TokenVerifier(settings, FakeJWKS())  # type: ignore[arg-type]
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[auth.get_verifier] = lambda: verifier
    app.dependency_overrides[deps.get_gateway] = lambda: pgw
    deps._session_cache.clear()
    roles.clear_membership_cache()
    ratelimit.reset()
    with TestClient(app) as client:
        yield client


def test_performance_endpoint_for_supervisor(api: TestClient) -> None:
    res = api.get("/v1/models/performance", params={"department_id": DEPT}, headers=auth_h(SUP))
    assert res.status_code == 200, res.text
    body = res.json()
    assert [m["version"] for m in body["active"]] == ["v2"]
    active = body["active"][0]
    assert active["holdout"]["mae"] == 0.82 and active["activated_by_role"] == "cli"
    assert active["feature_sets"]["core"]["mae"] == 6.8
    assert active["card"]["intended_use"].endswith("Model estimate, not a guarantee.")
    assert body["live"]["days"] == 1 and body["live"]["mae"] == 0.5
    assert body["registry"] is None  # registry table is for platform admins


def test_platform_admin_sees_registry(api: TestClient) -> None:
    res = api.get(
        "/v1/models/performance", params={"department_id": DEPT}, headers=auth_h(PLATFORM)
    )
    reg = res.json()["registry"]
    assert [r["version"] for r in reg] == ["v2", "v1"]
    assert reg[1]["activated_by_role"] == "platform_admin"


def test_technician_cannot_read_performance(api: TestClient) -> None:
    res = api.get("/v1/models/performance", params={"department_id": DEPT}, headers=auth_h(TECH))
    assert res.status_code == 403


def test_rollback_needs_platform_admin_and_fresh_totp(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert api.post("/v1/models/rollback", json={}, headers=auth_h(SUP)).status_code == 403
    stale = [{"method": "totp", "timestamp": int(time.time()) - 3600}]
    res = api.post("/v1/models/rollback", json={}, headers=auth_h(PLATFORM, amr=stale))
    assert res.status_code == 401

    calls: list[tuple[str, dict[str, Any]]] = []

    async def fake_rpc(self: Any, fn: str, args: dict[str, Any] | None = None) -> httpx.Response:
        calls.append((fn, args or {}))
        row = {
            "version": "v1",
            "feature_set": "full",
            "status": "active",
            "gates_passed": True,
            "created_at": "2026-10-25T00:00:00+00:00",
            "activated_at": "2026-11-23T00:00:00+00:00",
            "metrics": {},
        }
        return httpx.Response(200, json=row)

    monkeypatch.setattr(service_client.ServiceClient, "_headers", lambda self: {})
    monkeypatch.setattr(service_client.ServiceClient, "rpc_response", fake_rpc)
    fresh = [{"method": "totp", "timestamp": int(time.time())}]
    res = api.post(
        "/v1/models/rollback", json={"feature_set": "full"}, headers=auth_h(PLATFORM, amr=fresh)
    )
    assert res.status_code == 200, res.text
    assert calls == [("rollback_model_version", {"p_feature_set": "full", "p_actor": PLATFORM})]
