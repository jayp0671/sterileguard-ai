"""GET and PUT /v1/plans/{plan_date} (SG-11). Any member reads; supervisors and department
admins write. Model inputs only: everything here is known before 7:00 AM."""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Depends, Query

from sg_api.core.roles import ALL_ROLES, DepartmentAccess, require_role
from sg_api.deps import get_gateway
from sg_api.services import plans
from sg_api.services.supabase import Gateway

router = APIRouter(prefix="/plans", tags=["plans"])

DEPARTMENT = Query(..., description="Department the plan belongs to")
READ = require_role(*ALL_ROLES)
WRITE = require_role("supervisor", "dept_admin")


@router.get("/{plan_date}", response_model=plans.PlanOut)
async def get_plan(
    plan_date: dt.date,
    department_id: str = DEPARTMENT,
    access: DepartmentAccess = Depends(READ),
    gw: Gateway = Depends(get_gateway),
) -> plans.PlanOut:
    return await plans.get_plan(gw, access.principal.token, access.department_id, plan_date)


@router.put("/{plan_date}", response_model=plans.PlanOut)
async def put_plan(
    plan_date: dt.date,
    body: plans.PlanPut,
    department_id: str = DEPARTMENT,
    access: DepartmentAccess = Depends(WRITE),
    gw: Gateway = Depends(get_gateway),
) -> plans.PlanOut:
    payload: Any = body
    return await plans.save_plan(
        gw,
        access.principal.token,
        access.principal.user_id,
        access.department_id,
        plan_date,
        payload,
    )
