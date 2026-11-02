"""Staffing scenarios (SG-19, plan §6.2, §12.6): run the engine on a saved plan, store the run,
and apply a chosen option to the plan, which recomputes the forecast.

The engine lives in sg_ml.scenarios; this module loads its inputs (the plan, department
settings, lags from approved actuals) and keeps the run. Every recommendation is a model
estimate, not a guarantee.
"""

from __future__ import annotations

import asyncio
import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from sg_api.core.errors import ApiError
from sg_api.core.logging import get_logger
from sg_api.services import forecasts
from sg_api.services.models import ModelService
from sg_api.services.plans import department, today_in
from sg_api.services.supabase import Gateway, Row
from sg_data.schema import TIER2_INPUTS
from sg_ml import scenarios as engine

log = get_logger("sg_api.scenarios")

DISCLAIMER = engine.DISCLAIMER
PLAN_CHANGED = "https://sterileguard.dev/problems/plan-changed"
NO_SCENARIO = "https://sterileguard.dev/problems/no-scenario"
Lever = Literal[
    "morning_staff_present",
    "aft_11_staff",
    "aft_13_staff",
    "outside_support_staff",
    "ot_available_staff",
]


class LeverBounds(BaseModel):
    min: int = Field(ge=0, le=30)
    max: int = Field(ge=0, le=30)


class TargetIn(BaseModel):
    type: Literal["p50_hours", "p_high"]
    value: float = Field(ge=0, le=60)

    @model_validator(mode="after")
    def _probability(self) -> TargetIn:
        if self.type == "p_high" and self.value > 1:
            raise ValueError("a p_high target is a probability between 0 and 1")
        return self


class ScenarioIn(BaseModel):
    department_id: str
    target_date: dt.date
    levers: dict[Lever, LeverBounds] | None = Field(
        None, description="Absolute headcount bounds per lever; defaults to +0..+2 staff"
    )
    target: TargetIn | None = Field(
        None,
        description="Defaults to the department alert threshold, else the top of Moderate",
    )


class ApplyIn(BaseModel):
    department_id: str
    option_id: str = Field(min_length=1, max_length=64)


class OptionOut(BaseModel):
    id: str
    values: dict[str, int]
    changes: dict[str, int]
    ot_p10: float
    ot_p50: float
    ot_p90: float
    burden_probs: dict[str, float]
    added_staff_hours: float
    meets_target: bool
    low_confidence: bool = Field(description="Staffing outside what the model saw in training")
    what_if: bool = Field(description="Changes staff willing to stay; never recommended")


class TargetOut(BaseModel):
    type: Literal["p50_hours", "p_high"]
    value: float


class ScenarioOut(BaseModel):
    id: str
    department_id: str
    target_date: dt.date
    forecast_id: str | None = None
    model_version: str
    base: OptionOut
    options: list[OptionOut]
    pareto_ids: list[str]
    minimum_change_id: str | None
    target: TargetOut
    message: str
    bounds: dict[str, list[int]]
    window_hours: dict[str, float]
    applied: bool = False
    applied_option_id: str | None = None
    applied_at: dt.datetime | None = None
    created_at: dt.datetime
    disclaimer: str = DISCLAIMER


class AppliedOut(BaseModel):
    scenario: ScenarioOut
    forecast: forecasts.ForecastOut


def to_out(row: Row) -> ScenarioOut:
    result = dict(row["result"])
    return ScenarioOut(
        id=str(row["id"]),
        department_id=str(row["department_id"]),
        target_date=row["target_date"],
        forecast_id=row.get("forecast_id"),
        model_version=row["model_version"],
        base=OptionOut(**result["base"]),
        options=[OptionOut(**o) for o in result["options"]],
        pareto_ids=result["pareto_ids"],
        minimum_change_id=result.get("minimum_change_id"),
        target=TargetOut(**result["target"]),
        message=result["message"],
        bounds=result["bounds"],
        window_hours=result["window_hours"],
        applied=bool(row.get("applied")),
        applied_option_id=row.get("applied_option_id"),
        applied_at=row.get("applied_at"),
        created_at=row["created_at"],
    )


async def _latest_forecast_id(gw: Gateway, token: str, dept: str, day: dt.date) -> str | None:
    rows = await gw.select(
        token,
        "forecasts",
        {
            "select": "id",
            "department_id": f"eq.{dept}",
            "target_date": f"eq.{day.isoformat()}",
            "order": "created_at.desc",
            "limit": "1",
        },
    )
    return str(rows[0]["id"]) if rows else None


async def run(
    gw: Gateway, token: str, user_id: str, body: ScenarioIn, service: ModelService
) -> ScenarioOut:
    model = service.get("full")
    if model is None:
        raise ApiError(
            503, "no active model is loaded; try again shortly", forecasts.MODEL_NOT_LOADED
        )
    dept, day = body.department_id, body.target_date
    plan = await forecasts._plan(gw, token, dept, day)
    settings, _ = await department(gw, token, dept)
    history = await forecasts.approved_actuals(
        gw,
        token,
        dept,
        day - dt.timedelta(days=forecasts.HISTORY_LOOKBACK_DAYS),
        day - dt.timedelta(days=1),
    )
    levers: dict[str, dict[str, int]] = {
        str(k): v.model_dump() for k, v in (body.levers or {}).items()
    }
    target = engine.Target(body.target.type, body.target.value) if body.target else None
    try:
        result = await asyncio.to_thread(
            engine.evaluate,
            model.artifact,
            forecasts.plan_row(plan, day, history),
            settings,
            model_version=model.version,
            levers=levers or None,
            target=target,
        )
    except engine.ScenarioError as exc:
        raise ApiError(422, str(exc)) from exc
    saved = await gw.insert(
        token,
        "scenarios",
        {
            "department_id": dept,
            "target_date": day.isoformat(),
            "forecast_id": await _latest_forecast_id(gw, token, dept, day),
            "model_version": model.version,
            "request": {
                **body.model_dump(mode="json", exclude={"department_id"}),
                "plan_id": plan.get("id"),
                "plan_updated_at": plan.get("updated_at"),
            },
            "result": result.to_dict(),
            "created_by": user_id,
        },
    )
    log.info(
        "scenario_run",
        department_id=dept,
        options=len(result.options),
        minimum=result.minimum_change_id,
        model_version=model.version,
    )
    return to_out(saved)


async def latest(gw: Gateway, token: str, dept: str, day: dt.date) -> ScenarioOut:
    rows = await gw.select(
        token,
        "scenarios",
        {
            "select": "*",
            "department_id": f"eq.{dept}",
            "target_date": f"eq.{day.isoformat()}",
            "order": "created_at.desc",
            "limit": "1",
        },
    )
    if not rows:
        raise ApiError(404, f"no scenario run yet for {day.isoformat()}", NO_SCENARIO)
    return to_out(rows[0])


async def _by_id(gw: Gateway, token: str, dept: str, scenario_id: str) -> Row:
    rows = await gw.select(
        token,
        "scenarios",
        {"select": "*", "id": f"eq.{scenario_id}", "department_id": f"eq.{dept}"},
    )
    if not rows:
        raise ApiError(404, "scenario not found")
    return rows[0]


async def apply(
    gw: Gateway,
    token: str,
    user_id: str,
    dept: str,
    scenario_id: str,
    option_id: str,
    service: ModelService,
) -> AppliedOut:
    """Copy one option's staffing into the plan, recompute the forecast (trigger 'scenario')
    and mark the run applied. Refused when the plan changed after the run."""
    row = await _by_id(gw, token, dept, scenario_id)
    scenario = to_out(row)
    option = next((o for o in scenario.options if o.id == option_id), None)
    if option is None:
        raise ApiError(422, "option_id is not one of this scenario's options")
    day = scenario.target_date
    _, tz = await department(gw, token, dept)
    if day <= today_in(tz):
        raise ApiError(422, "this date has started or passed; scenarios apply to future plans")
    plan = await forecasts._plan(gw, token, dept, day)
    request = row.get("request") or {}
    if str(plan.get("updated_at")) != str(request.get("plan_updated_at")):
        raise ApiError(
            409, "the plan changed after this scenario was run; run it again", PLAN_CHANGED
        )
    patch: Row = {"updated_by": user_id}
    for lever, value in option.values.items():
        patch[lever] = value
        if lever in TIER2_INPUTS:
            patch[f"{lever}__missing"] = False
    await gw.update(token, "shift_plans", {"id": f"eq.{plan['id']}"}, patch)
    forecast = await forecasts.compute(gw, token, user_id, dept, day, service, trigger="scenario")
    updated = await gw.update(
        token,
        "scenarios",
        {"id": f"eq.{scenario_id}"},
        {
            "applied": True,
            "applied_option_id": option_id,
            "applied_at": dt.datetime.now(dt.UTC).isoformat(),
            "applied_by": user_id,
        },
    )
    log.info("scenario_applied", department_id=dept, scenario_id=scenario_id, option=option_id)
    return AppliedOut(scenario=to_out(updated[0] if updated else row), forecast=forecast)
