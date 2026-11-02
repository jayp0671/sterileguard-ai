"""SG-19: scenario endpoints with the tiny synthetic model (no real data)."""

from __future__ import annotations

import datetime as dt
import json
import uuid
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from sg_api import deps
from sg_api.core import auth, ratelimit, roles
from sg_api.core.config import Settings, get_settings
from sg_api.main import create_app
from sg_api.services import scenarios
from sg_api.services.models import ModelService
from sg_api.services.supabase import SupabaseGateway

from .test_forecasts_api import TARGET, ForecastGateway, service  # noqa: F401
from .test_security_plans import DEPT, SUP, TECH, auth_h

UPDATED_AT = "2026-11-02T20:00:00+00:00"


class ScenarioGateway(ForecastGateway):
    def __init__(self) -> None:
        super().__init__()
        self.rows["scenarios"] = []
        self.updates: list[tuple[str, dict[str, str], dict[str, Any]]] = []

    def plan(self, day: dt.date, status: str = "final") -> None:
        super().plan(day, status)
        self.plans[(DEPT, day.isoformat())]["updated_at"] = UPDATED_AT

    async def select(self, token_: str, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        if table == "scenarios":
            eq = {k: v.removeprefix("eq.") for k, v in params.items() if v.startswith("eq.")}
            out = [
                r for r in self.rows["scenarios"] if all(str(r.get(k)) == v for k, v in eq.items())
            ]
            return sorted(out, key=lambda r: r["created_at"], reverse=True)
        return await super().select(token_, table, params)

    async def insert(self, token_: str, table: str, row: dict[str, Any]) -> dict[str, Any]:
        # What PostgREST would store: JSON only.
        return await super().insert(token_, table, json.loads(json.dumps(row)))

    async def update(
        self, token_: str, table: str, params: dict[str, str], patch: dict[str, Any]
    ) -> list[dict[str, Any]]:
        self.updates.append((table, params, patch))
        row_id = params["id"].removeprefix("eq.")
        if table == "shift_plans":
            for plan in self.plans.values():
                if plan["id"] == row_id:
                    plan.update(patch, updated_at="2026-11-02T21:00:00+00:00")
                    return [plan]
        for r in self.rows.get(table, []):
            if r["id"] == row_id:
                r.update(patch)
                return [r]
        return []


@pytest.fixture
def gw() -> ScenarioGateway:
    return ScenarioGateway()


@pytest.fixture
def api(gw: ScenarioGateway, service: ModelService) -> Iterator[TestClient]:  # noqa: F811
    settings = Settings(env="test", supabase_url="http://db.invalid:54321")
    app = create_app(settings)
    app.state.model_service = service
    verifier = auth.TokenVerifier(settings, _jwks())
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[auth.get_verifier] = lambda: verifier
    app.dependency_overrides[deps.get_gateway] = lambda: gw
    deps._session_cache.clear()
    roles.clear_membership_cache()
    ratelimit.reset()
    with TestClient(app) as client:
        yield client


def _jwks() -> Any:
    from .test_security_plans import FakeJWKS

    return FakeJWKS()


def run(api: TestClient, who: str = SUP, **body: Any) -> httpx.Response:
    resp: httpx.Response = api.post(
        "/v1/scenarios",
        json={"department_id": DEPT, "target_date": TARGET.isoformat(), **body},
        headers=auth_h(who),
    )
    return resp


def test_run_returns_options_and_recommendation(api: TestClient, gw: ScenarioGateway) -> None:
    gw.plan(TARGET)
    resp = run(api)
    assert resp.status_code == 201, resp.text
    out = resp.json()
    assert out["disclaimer"] == "Model estimate, not a guarantee."
    assert len(out["options"]) == 81 * 4  # 3 morning staff: volunteers 0..3
    assert out["base"]["changes"] == {k: 0 for k in out["base"]["changes"]}
    assert out["target"]["type"] == "p50_hours"
    assert out["window_hours"]["aft_11_staff"] == pytest.approx(4)
    ids = {o["id"] for o in out["options"]}
    assert set(out["pareto_ids"]) <= ids
    if out["minimum_change_id"]:
        assert out["minimum_change_id"] in ids
    saved = gw.rows["scenarios"][0]
    assert saved["created_by"] == SUP and saved["request"]["plan_updated_at"] == UPDATED_AT


def test_no_plan_is_409(api: TestClient) -> None:
    resp = run(api)
    assert resp.status_code == 409
    assert resp.json()["type"].endswith("no-plan")


def test_technicians_read_but_cannot_run_or_apply(api: TestClient, gw: ScenarioGateway) -> None:
    gw.plan(TARGET)
    assert run(api, TECH).status_code == 403
    sid = run(api).json()["id"]
    latest = api.get(
        "/v1/scenarios/latest",
        params={"department_id": DEPT, "target_date": TARGET.isoformat()},
        headers=auth_h(TECH),
    )
    assert latest.status_code == 200 and latest.json()["id"] == sid
    resp = api.post(
        f"/v1/scenarios/{sid}/apply",
        json={"department_id": DEPT, "option_id": "x"},
        headers=auth_h(TECH),
    )
    assert resp.status_code == 403


def test_bad_bounds_and_targets_are_422(api: TestClient, gw: ScenarioGateway) -> None:
    gw.plan(TARGET)
    wide = {k: {"min": 0, "max": 9} for k in ("morning_staff_present", "aft_11_staff")}
    assert run(api, levers=wide).status_code == 422
    assert run(api, levers={"regular_patients": {"min": 0, "max": 1}}).status_code == 422
    assert run(api, target={"type": "p_high", "value": 1.5}).status_code == 422


def test_custom_target_and_unreachable_message(api: TestClient, gw: ScenarioGateway) -> None:
    gw.plan(TARGET)
    out = run(api, target={"type": "p50_hours", "value": 0}).json()
    if out["minimum_change_id"] is None:
        assert out["message"].startswith("Even with")
    out = run(api, target={"type": "p_high", "value": 1}).json()
    assert out["minimum_change_id"] == out["base"]["id"]


def test_apply_updates_plan_recomputes_and_marks_applied(
    api: TestClient, gw: ScenarioGateway
) -> None:
    gw.plan(TARGET)
    out = run(api).json()
    option = next(
        o for o in out["options"] if o["changes"]["aft_11_staff"] == 1 and not o["what_if"]
    )
    resp = api.post(
        f"/v1/scenarios/{out['id']}/apply",
        json={"department_id": DEPT, "option_id": option["id"]},
        headers=auth_h(SUP),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["scenario"]["applied"] is True
    assert body["scenario"]["applied_option_id"] == option["id"]
    assert body["forecast"]["trigger"] == "scenario"
    plan = gw.plans[(DEPT, TARGET.isoformat())]
    assert plan["aft_11_staff"] == option["values"]["aft_11_staff"]
    assert plan["aft_11_staff__missing"] is False
    assert body["forecast"]["ot_p50"] == pytest.approx(option["ot_p50"], abs=0.01)
    # The plan changed, so applying the same run again is refused.
    again = api.post(
        f"/v1/scenarios/{out['id']}/apply",
        json={"department_id": DEPT, "option_id": option["id"]},
        headers=auth_h(SUP),
    )
    assert again.status_code == 409
    assert again.json()["type"].endswith("plan-changed")


def test_apply_unknown_option_or_scenario(api: TestClient, gw: ScenarioGateway) -> None:
    gw.plan(TARGET)
    sid = run(api).json()["id"]
    bad = api.post(
        f"/v1/scenarios/{sid}/apply",
        json={"department_id": DEPT, "option_id": "nope"},
        headers=auth_h(SUP),
    )
    assert bad.status_code == 422
    missing = api.post(
        f"/v1/scenarios/{uuid.uuid4()}/apply",
        json={"department_id": DEPT, "option_id": "nope"},
        headers=auth_h(SUP),
    )
    assert missing.status_code == 404


def test_latest_without_runs_is_404(api: TestClient) -> None:
    resp = api.get(
        "/v1/scenarios/latest",
        params={"department_id": DEPT, "target_date": TARGET.isoformat()},
        headers=auth_h(SUP),
    )
    assert resp.status_code == 404
    assert resp.json()["type"].endswith("no-scenario")


async def test_run_through_the_real_supabase_gateway(service: ModelService) -> None:  # noqa: F811
    """The real gateway (not a fake) carries the run: the stored payload must be plain JSON."""
    seen: dict[str, Any] = {}
    plan_gw = ScenarioGateway()
    plan_gw.plan(TARGET)
    plan = plan_gw.plans[(DEPT, TARGET.isoformat())]

    def handle(req: httpx.Request) -> httpx.Response:
        table = req.url.path.rsplit("/", 1)[-1]
        if req.method == "POST" and table == "scenarios":
            seen["body"] = json.loads(req.content)
            row = {
                **seen["body"],
                "id": str(uuid.uuid4()),
                "created_at": "2026-11-02T22:00:00+00:00",
            }
            return httpx.Response(201, json=[row])
        if table == "shift_plans":
            return httpx.Response(200, json=[plan])
        if table == "departments":
            return httpx.Response(
                200, json=[{"settings": {}, "facilities": {"timezone": "America/New_York"}}]
            )
        return httpx.Response(200, json=[])

    settings = Settings(env="test", supabase_url="http://sb.test", supabase_anon_key="anon")
    gw = SupabaseGateway(settings, httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    body = scenarios.ScenarioIn(department_id=DEPT, target_date=TARGET, levers=None, target=None)
    out = await scenarios.run(gw, "user-tok", SUP, body, service)
    assert out.options and seen["body"]["result"]["options"]
    assert seen["body"]["forecast_id"] is None
