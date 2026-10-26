"""SG-15: forecast endpoints with a tiny model trained on synthetic rows (no real data)."""

from __future__ import annotations

import datetime as dt
import time
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from sg_api import deps
from sg_api.core import auth, ratelimit, roles
from sg_api.core.config import Settings, get_settings
from sg_api.main import create_app
from sg_api.services import forecasts
from sg_api.services.models import ModelService, build
from sg_ml.testing import tiny_artifact_bytes

from .test_security_plans import DEPT, SUP, TECH, FakeGateway, FakeJWKS, auth_h

NY = dt.timezone(dt.timedelta(hours=-4))


def today() -> dt.date:
    return dt.datetime.now(NY).date()


TARGET = forecasts.next_workday(today())


class ForecastGateway(FakeGateway):
    def __init__(self) -> None:
        super().__init__()
        self.rows: dict[str, list[dict[str, Any]]] = {"forecasts": [], "forecast_drivers": []}
        self.actuals: list[dict[str, Any]] = []

    def plan(self, day: dt.date, status: str = "final") -> None:
        self.plans[(DEPT, day.isoformat())] = {
            "id": str(uuid.uuid4()),
            "department_id": DEPT,
            "plan_date": day.isoformat(),
            "status": status,
            "regular_patients": 420,
            "morning_staff_present": 3,
            "mf_cases": 22,
            "student_clinic_sessions": 4,
            "aft_11_staff": 2,
            "aft_13_staff": 1,
            "aft_15_staff": 2,
            "outside_support_staff": 1,
            "ot_available_staff": 2,
            "washers_up": 2,
            "sterilizers_up": 1,
            "carryover_backlog_estimate": 2,
            "is_holiday": False,
            "academic_event": "none",
        }

    async def select(self, token_: str, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        eq = {k: v.removeprefix("eq.") for k, v in params.items() if v.startswith("eq.")}
        if table == "shift_actuals":
            return self.actuals
        if table == "forecasts":
            out = [
                r
                for r in self.rows["forecasts"]
                if all(str(r.get(k)) == v for k, v in eq.items() if k in r)
            ]
            out = sorted(out, key=lambda r: r["created_at"], reverse=True)
            if "forecast_drivers" in params.get("select", ""):
                out = [
                    {
                        **r,
                        "forecast_drivers": [
                            d for d in self.rows["forecast_drivers"] if d["forecast_id"] == r["id"]
                        ],
                    }
                    for r in out
                ]
            return out[: int(params.get("limit", "100"))]
        return await super().select(token_, table, params)

    async def insert(self, token_: str, table: str, row: dict[str, Any]) -> dict[str, Any]:
        saved = {
            **row,
            "id": str(uuid.uuid4()),
            "created_at": dt.datetime.now(dt.UTC).isoformat(),
        }
        self.rows[table].append(saved)
        return saved

    async def insert_many(
        self, token_: str, table: str, rows: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        self.rows[table].extend(rows)
        return rows


@pytest.fixture(scope="module")
def service() -> ModelService:
    s = ModelService(source=None)
    s.swap({"full": build("v-test", "full", tiny_artifact_bytes(7))})
    return s


@pytest.fixture
def gw() -> ForecastGateway:
    return ForecastGateway()


@pytest.fixture
def api(gw: ForecastGateway, service: ModelService) -> Iterator[TestClient]:
    settings = Settings(env="test", supabase_url="http://db.invalid:54321")
    app = create_app(settings)
    app.state.model_service = service
    verifier = auth.TokenVerifier(settings, FakeJWKS())  # type: ignore[arg-type]
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[auth.get_verifier] = lambda: verifier
    app.dependency_overrides[deps.get_gateway] = lambda: gw
    deps._session_cache.clear()
    roles.clear_membership_cache()
    ratelimit.reset()
    with TestClient(app) as client:
        yield client


def post(api: TestClient, who: str = SUP, day: dt.date = TARGET) -> Any:
    return api.post(
        "/v1/forecasts",
        json={"department_id": DEPT, "target_date": day.isoformat()},
        headers=auth_h(who),
    )


def test_no_plan_is_409(api: TestClient) -> None:
    resp = post(api)
    assert resp.status_code == 409
    assert resp.json()["type"].endswith("no-plan")


def test_compute_returns_range_class_and_drivers(api: TestClient, gw: ForecastGateway) -> None:
    gw.plan(TARGET)
    gw.actuals = [
        {
            "shift_date": (TARGET - dt.timedelta(days=3)).isoformat(),
            "ot_labor_hours": 9.5,
            "source": "simulated",
        },
        {
            "shift_date": (TARGET - dt.timedelta(days=3)).isoformat(),
            "ot_labor_hours": 7.0,
            "source": "real",
        },
    ]
    resp = post(api)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert 0 <= body["ot_p10"] <= body["ot_p50"] <= body["ot_p90"]
    assert body["burden_class"] in ("low", "moderate", "high")
    assert sum(body["burden_probs"].values()) == pytest.approx(1, abs=0.01)
    assert body["thresholds"]["source"] == "simulated_provisional"
    assert body["disclaimer"] == "Model estimate, not a guarantee."
    drivers = body["drivers"]
    assert len(drivers) >= 3 and drivers[-1]["feature"] == "other"
    assert all(d["text_key"].startswith("drivers.") and d["default_text"] for d in drivers)
    assert body["model_version"] == "v-test" and body["trigger"] == "manual"
    saved = gw.rows["forecasts"][0]
    assert (
        saved["created_by"] == SUP
        and saved["plan_id"] == gw.plans[(DEPT, TARGET.isoformat())]["id"]
    )
    assert len(gw.rows["forecast_drivers"]) == len(drivers)


def test_real_actual_wins_for_lags() -> None:
    import asyncio

    gw = ForecastGateway()
    day = dt.date(2026, 11, 2)
    gw.actuals = [
        {"shift_date": "2026-10-30", "ot_labor_hours": 9.5, "source": "real"},
        {"shift_date": "2026-10-30", "ot_labor_hours": 1.0, "source": "simulated"},
    ]
    got = asyncio.run(forecasts.approved_actuals(gw, "t", DEPT, day - dt.timedelta(days=10), day))
    assert got == {dt.date(2026, 10, 30): 9.5}


def test_technicians_read_but_cannot_compute(api: TestClient, gw: ForecastGateway) -> None:
    gw.plan(TARGET)
    assert post(api, TECH).status_code == 403
    missing = api.get(
        "/v1/forecasts/next-day", params={"department_id": DEPT}, headers=auth_h(TECH)
    )
    assert missing.status_code == 404 and missing.json()["type"].endswith("no-forecast")
    created = post(api).json()
    got = api.get("/v1/forecasts/next-day", params={"department_id": DEPT}, headers=auth_h(TECH))
    assert got.status_code == 200 and got.json()["id"] == created["id"]
    one = api.get(
        f"/v1/forecasts/{created['id']}", params={"department_id": DEPT}, headers=auth_h(TECH)
    )
    assert one.status_code == 200 and len(one.json()["drivers"]) == len(created["drivers"])


def test_history_pairs_forecasts_with_actuals(api: TestClient, gw: ForecastGateway) -> None:
    day = today() - dt.timedelta(days=2)
    gw.rows["forecasts"] = [
        {
            "id": "a",
            "target_date": day.isoformat(),
            "ot_p10": 1,
            "ot_p50": 2,
            "ot_p90": 3,
            "model_version": "v1",
            "created_at": "2026-10-20T10:00:00+00:00",
        },
        {
            "id": "b",
            "target_date": day.isoformat(),
            "ot_p10": 2,
            "ot_p50": 3,
            "ot_p90": 4,
            "model_version": "v2",
            "created_at": "2026-10-20T12:00:00+00:00",
        },
    ]
    gw.actuals = [{"shift_date": day.isoformat(), "ot_labor_hours": 2.5, "source": "real"}]
    resp = api.get(
        "/v1/forecasts/history", params={"department_id": DEPT, "days": 14}, headers=auth_h(TECH)
    )
    assert resp.status_code == 200
    assert resp.json() == [
        {
            "date": day.isoformat(),
            "ot_p10": 2.0,
            "ot_p50": 3.0,
            "ot_p90": 4.0,
            "actual": 2.5,
            "model_version": "v2",
        }
    ]


def test_no_model_loaded_is_503(gw: ForecastGateway) -> None:
    settings = Settings(env="test", supabase_url="http://db.invalid:54321")
    app = create_app(settings)
    app.state.model_service = ModelService(source=None)
    verifier = auth.TokenVerifier(settings, FakeJWKS())  # type: ignore[arg-type]
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[auth.get_verifier] = lambda: verifier
    app.dependency_overrides[deps.get_gateway] = lambda: gw
    roles.clear_membership_cache()
    gw.plan(TARGET)
    with TestClient(app) as client:
        resp = post(client)
    assert resp.status_code == 503 and resp.json()["type"].endswith("model-not-loaded")


def test_warm_compute_is_fast(api: TestClient, gw: ForecastGateway) -> None:
    gw.plan(TARGET)
    post(api)  # warm
    times = []
    for _ in range(20):
        t0 = time.perf_counter()
        assert post(api).status_code == 201
        times.append(time.perf_counter() - t0)
    times.sort()
    assert times[int(0.95 * len(times)) - 1] < 1.0


def test_next_workday_skips_weekends() -> None:
    assert forecasts.next_workday(dt.date(2026, 10, 30)) == dt.date(2026, 11, 2)  # Fri -> Mon
    assert forecasts.next_workday(dt.date(2026, 10, 26)) == dt.date(2026, 10, 27)
