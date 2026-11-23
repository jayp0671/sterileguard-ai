"""SG-23: POST /v1/agents/briefing. No network: the NIM client uses scripted transports."""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from sg_agents.nim import Completion, NimClient, TransportError, load_config
from sg_api import deps
from sg_api.core import auth, ratelimit, roles
from sg_api.core.config import Settings, get_settings
from sg_api.core.errors import ApiError
from sg_api.main import create_app
from sg_api.routers import agents as agents_router
from sg_api.services.agents import AgentService
from sg_api.services.forecasts import DriverOut, ForecastOut, Thresholds

from .test_security_plans import DEPT, OTHER, TECH, FakeGateway, FakeJWKS, auth_h

FID = "50000000-0000-4000-8000-0000000000f1"


def forecast(dept: str = DEPT) -> ForecastOut:
    return ForecastOut(
        id=FID,
        department_id=dept,
        target_date=dt.date(2026, 11, 24),
        model_version="v",
        feature_set="full",
        ot_p10=10.94,
        ot_p50=11.76,
        ot_p90=12.51,
        burden_class="moderate",
        burden_probs={"moderate": 0.7, "high": 0.2, "low": 0.1},
        thresholds=Thresholds(low_max=5.67, moderate_max=12.13, source="simulated_provisional"),
        trigger="manual",
        created_at=dt.datetime(2026, 11, 23, 20, tzinfo=dt.UTC),
        drivers=[
            DriverOut(
                rank=1,
                feature="regular_patients",
                contribution_hours=2.1,
                text_key="k",
                text_params={},
                default_text="More patients than usual (380 scheduled)",
            ),
            DriverOut(
                rank=2,
                feature="ot_available_staff",
                contribution_hours=1.4,
                text_key="k",
                text_params={},
                default_text="Only 2 staff willing to stay late",
            ),
        ],
    )


class Scripted:
    def __init__(self, *answers: Any) -> None:
        self.answers = list(answers)
        self.calls = 0

    async def complete(self, model: str, messages: list[dict[str, str]], **kw: Any) -> Completion:
        self.calls += 1
        a = self.answers.pop(0) if self.answers else "x"
        if isinstance(a, Exception):
            raise a
        return Completion(a)


@pytest.fixture
def make_api(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    clients: list[TestClient] = []

    async def by_id(gw: Any, token: str, fid: str) -> ForecastOut:
        if fid != FID:
            raise ApiError(404, "forecast not found")
        return forecast()

    async def no_scenario(*a: Any, **k: Any) -> Any:
        raise ApiError(404, "no scenario")

    monkeypatch.setattr(agents_router.fc_svc, "by_id", by_id)
    monkeypatch.setattr(agents_router.sc_svc, "latest", no_scenario)

    def build(transport: Any | None, mode: str = "live") -> TestClient:
        settings = Settings(env="test", supabase_url="http://db.invalid:54321")
        app = create_app(settings)
        nim = NimClient(
            load_config(), mode=mode, api_key="k" if transport else "", transport=transport
        )  # type: ignore[arg-type]
        app.state.agent_service = AgentService(settings, nim)
        verifier = auth.TokenVerifier(settings, FakeJWKS())  # type: ignore[arg-type]
        gw = FakeGateway()
        gw.memberships.append({"user_id": TECH, "department_id": OTHER, "role": "technician"})
        app.dependency_overrides[get_settings] = lambda: settings
        app.dependency_overrides[auth.get_verifier] = lambda: verifier
        app.dependency_overrides[deps.get_gateway] = lambda: gw
        deps._session_cache.clear()
        roles.clear_membership_cache()
        ratelimit.reset()
        c = TestClient(app)
        c.__enter__()
        clients.append(c)
        return c

    yield build
    for c in clients:
        c.__exit__(None, None, None)


def ask(api: TestClient, locale: str = "en", dept: str = DEPT) -> Any:
    return api.post(
        "/v1/agents/briefing",
        json={"department_id": dept, "forecast_id": FID, "locale": locale},
        headers=auth_h(TECH),
    )


def test_nim_off_returns_the_template(make_api: Any) -> None:
    res = ask(make_api(None, mode="off"))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["source"] == "template"
    assert body["text"].startswith(
        "Tomorrow's overtime is most likely 11.8 hours (range 10.9 to 12.5)"
    )
    assert body["text"].endswith("Model estimate.")
    assert body["disclaimer"] == "Model estimate, not a guarantee."


def test_good_llm_answer_is_used_and_cached(make_api: Any) -> None:
    good = (
        "Tomorrow likely brings 11.8 overtime hours (10.9 to 12.5), a moderate day, "
        "mostly from more patients than usual. Model estimate."
    )
    t = Scripted(good)
    api = make_api(t)
    first, second = ask(api).json(), ask(api).json()
    assert first["source"] == "llm" and first["text"] == good
    assert first["model"] == "meta/llama-3.3-70b-instruct" and first["prompt_version"] == "v1"
    assert second == first and t.calls == 1  # cached per forecast and locale


@pytest.mark.parametrize(
    "bad",
    [
        "Tomorrow likely brings 13 overtime hours. Model estimate.",
        "Ask Dr. Okafor to stay; 11.8 hours expected. Model estimate.",
        "11.8 hours expected, see https://example.com. Model estimate.",
        "11.8 hours expected tomorrow.",
    ],
)
def test_guardrail_rejections_fall_back(make_api: Any, bad: str) -> None:
    body = ask(make_api(Scripted(bad))).json()
    assert body["source"] == "template"


def test_nim_down_still_answers(make_api: Any) -> None:
    t = Scripted(*[TransportError(503)] * 10)
    body = ask(make_api(t)).json()
    assert body["source"] == "template" and t.calls == 4


def test_other_department_gets_404(make_api: Any) -> None:
    assert ask(make_api(None, mode="off"), dept=OTHER).status_code == 404


def test_spanish_template(make_api: Any) -> None:
    body = ask(make_api(None, mode="off"), locale="es").json()
    assert body["text"].endswith("Estimación del modelo.") and "11,8" in body["text"]
