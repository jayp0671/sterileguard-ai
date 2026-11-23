"""Agent endpoints (SG-23, plan §13). Rate limited to 10 a minute per user (core.ratelimit)."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from sg_api.core.errors import ApiError
from sg_api.core.roles import ALL_ROLES, DepartmentAccess, require_role
from sg_api.deps import get_gateway
from sg_api.services import forecasts as fc_svc
from sg_api.services import scenarios as sc_svc
from sg_api.services.agents import AgentService
from sg_api.services.supabase import Gateway
from sg_ml.scenarios import describe_changes

router = APIRouter(prefix="/agents", tags=["agents"])
READ = require_role(*ALL_ROLES)
DISCLAIMER = "Model estimate, not a guarantee."


class BriefingIn(BaseModel):
    department_id: UUID
    forecast_id: UUID
    locale: Literal["en", "es"] = "en"


class BriefingOut(BaseModel):
    text: str
    source: Literal["llm", "template"]
    model: str | None = None
    prompt_version: str
    disclaimer: str = DISCLAIMER
    ai_note: str = Field(
        default=(
            "An AI model rewrote the forecast numbers above into plain sentences. It does not "
            "predict, and its answer is checked so it can only use numbers from the forecast."
        )
    )


def get_agent_service(request: Request) -> AgentService:
    service: AgentService = request.app.state.agent_service
    return service


async def _minimum_change(
    gw: Gateway, token: str, dept: str, forecast: Any
) -> dict[str, Any] | None:
    """The recommended (minimum) change of the latest scenario run for that forecast's date,
    only when it is a real change and the run is for this forecast's inputs."""
    try:
        sc = await sc_svc.latest(gw, token, dept, forecast.target_date)
    except ApiError:
        return None
    if not sc.minimum_change_id or sc.minimum_change_id == sc.base.id:
        return None
    if sc.forecast_id and sc.forecast_id != forecast.id:
        return None
    best = next((o for o in sc.options if o.id == sc.minimum_change_id), None)
    if best is None or best.what_if:
        return None
    return {
        "text": describe_changes(best.changes),
        "from_p50": sc.base.ot_p50,
        "to_p50": best.ot_p50,
    }


@router.post("/briefing", response_model=BriefingOut)
async def create_briefing(
    body: BriefingIn,
    access: DepartmentAccess = Depends(READ),
    gw: Gateway = Depends(get_gateway),
    agents: AgentService = Depends(get_agent_service),
) -> BriefingOut:
    """A 3 to 4 sentence summary of a forecast. AI-written when NVIDIA NIM is available and
    the answer passes the number guardrail; otherwise the fixed template."""
    forecast = await fc_svc.by_id(gw, access.principal.token, str(body.forecast_id))
    if forecast.department_id != access.department_id:
        raise ApiError(404, "forecast not found")
    mc = await _minimum_change(gw, access.principal.token, access.department_id, forecast)
    out = await agents.briefing(forecast.model_dump(mode="json"), body.locale, mc)
    return BriefingOut(**out)
