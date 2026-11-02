"""Scenario endpoints (SG-19, plan §7.2). Members read the latest run; supervisors and
department admins run and apply. Rate limit 30 per minute (core.ratelimit). Every
recommendation is a model estimate, not a guarantee."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Query

from sg_api.core.roles import ALL_ROLES, DepartmentAccess, require_role
from sg_api.deps import get_gateway
from sg_api.routers.models import get_model_service
from sg_api.services import scenarios
from sg_api.services.models import ModelService
from sg_api.services.supabase import Gateway

router = APIRouter(prefix="/scenarios", tags=["scenarios"])

READ = require_role(*ALL_ROLES)
WRITE = require_role("supervisor", "dept_admin")
DEPARTMENT = Query(..., description="Department the scenario belongs to")


@router.post("", response_model=scenarios.ScenarioOut, status_code=201)
async def run_scenario(
    body: scenarios.ScenarioIn,
    access: DepartmentAccess = Depends(WRITE),
    gw: Gateway = Depends(get_gateway),
    service: ModelService = Depends(get_model_service),
) -> scenarios.ScenarioOut:
    """Evaluate every staffing option within the bounds for the saved plan of target_date,
    store the run and return the options, the Pareto front and the minimum change."""
    return await scenarios.run(gw, access.principal.token, access.principal.user_id, body, service)


@router.get("/latest", response_model=scenarios.ScenarioOut)
async def latest_scenario(
    target_date: dt.date,
    department_id: str = DEPARTMENT,
    access: DepartmentAccess = Depends(READ),
    gw: Gateway = Depends(get_gateway),
) -> scenarios.ScenarioOut:
    """The most recent run for a date (404 no-scenario)."""
    return await scenarios.latest(gw, access.principal.token, access.department_id, target_date)


@router.post("/{scenario_id}/apply", response_model=scenarios.AppliedOut)
async def apply_scenario(
    scenario_id: str,
    body: scenarios.ApplyIn,
    access: DepartmentAccess = Depends(WRITE),
    gw: Gateway = Depends(get_gateway),
    service: ModelService = Depends(get_model_service),
) -> scenarios.AppliedOut:
    """Copy the option's staffing into the plan, recompute the forecast and mark the run
    applied (409 plan-changed when the plan was edited after the run)."""
    return await scenarios.apply(
        gw,
        access.principal.token,
        access.principal.user_id,
        access.department_id,
        scenario_id,
        body.option_id,
        service,
    )
