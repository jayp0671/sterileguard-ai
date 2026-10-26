"""Forecast endpoints (SG-15, plan §7.2). Every member reads; supervisors and department
admins compute. Each forecast is a model estimate, not a guarantee."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from sg_api.core.errors import ApiError
from sg_api.core.roles import ALL_ROLES, DepartmentAccess, require_role
from sg_api.deps import get_gateway
from sg_api.routers.models import get_model_service
from sg_api.services import forecasts
from sg_api.services.models import ModelService
from sg_api.services.supabase import Gateway

router = APIRouter(prefix="/forecasts", tags=["forecasts"])

READ = require_role(*ALL_ROLES)
WRITE = require_role("supervisor", "dept_admin")
DEPARTMENT = Query(..., description="Department the forecast belongs to")


@router.post("", response_model=forecasts.ForecastOut, status_code=201)
async def create_forecast(
    body: forecasts.ForecastIn,
    access: DepartmentAccess = Depends(WRITE),
    gw: Gateway = Depends(get_gateway),
    service: ModelService = Depends(get_model_service),
) -> forecasts.ForecastOut:
    """Compute from the saved plan for target_date (409 no-plan without one)."""
    return await forecasts.compute(
        gw,
        access.principal.token,
        access.principal.user_id,
        access.department_id,
        body.target_date,
        service,
    )


@router.get("/next-day", response_model=forecasts.ForecastOut)
async def next_day_forecast(
    department_id: str = DEPARTMENT,
    access: DepartmentAccess = Depends(READ),
    gw: Gateway = Depends(get_gateway),
) -> forecasts.ForecastOut:
    """Latest forecast for the next workday in the department's time zone (404 no-forecast)."""
    return await forecasts.next_day(gw, access.principal.token, access.department_id)


@router.get("/history", response_model=list[forecasts.HistoryPoint])
async def forecast_history(
    department_id: str = DEPARTMENT,
    days: int = Query(14, ge=1, le=90),
    access: DepartmentAccess = Depends(READ),
    gw: Gateway = Depends(get_gateway),
) -> list[forecasts.HistoryPoint]:
    """Latest forecast per day for the last `days` days, with approved actuals."""
    return await forecasts.history(gw, access.principal.token, access.department_id, days)


@router.get("/{forecast_id}", response_model=forecasts.ForecastOut)
async def get_forecast(
    forecast_id: str,
    department_id: str = DEPARTMENT,
    access: DepartmentAccess = Depends(READ),
    gw: Gateway = Depends(get_gateway),
) -> forecasts.ForecastOut:
    """One forecast with its drivers. RLS decides visibility; the department must match."""
    out = await forecasts.by_id(gw, access.principal.token, forecast_id)
    if out.department_id != access.department_id:
        raise ApiError(404, "forecast not found")
    return out
