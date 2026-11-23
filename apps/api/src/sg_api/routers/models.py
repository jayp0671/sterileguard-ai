"""Model registry endpoints (SG-14, plan §7.2, §12.7)."""

from __future__ import annotations

import datetime as dt
import hmac
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel, Field

from sg_api.core.auth import check_recent_totp
from sg_api.core.config import Settings, get_settings
from sg_api.core.errors import ApiError
from sg_api.core.logging import get_logger
from sg_api.core.roles import (
    UUID_PATTERN,
    DepartmentAccess,
    GlobalAccess,
    require_any_role,
    require_role,
)
from sg_api.db.service_client import ServiceClient
from sg_api.deps import get_gateway
from sg_api.services import performance as perf
from sg_api.services import plans as plan_svc
from sg_api.services.models import ModelService
from sg_api.services.supabase import Gateway

router = APIRouter(prefix="/models", tags=["models"])
internal = APIRouter(prefix="/internal", tags=["internal"], include_in_schema=False)
log = get_logger("sg_api.audit")

SUPERVISOR_AND_ABOVE = ("supervisor", "dept_admin", "platform_admin")
GATES_NOT_PASSED = "https://sterileguard.dev/problems/gates-not-passed"
READ = require_any_role(*SUPERVISOR_AND_ABOVE)
ADMIN = require_any_role("platform_admin")
# Ticket: supervisor and above; the nav (SG-10) also shows it to data stewards, who own data
# quality, so they read it too.
PERF = require_role("supervisor", "dept_admin", "data_steward", "platform_admin")


class ModelVersionOut(BaseModel):
    version: str
    feature_set: Literal["full", "core"]
    status: Literal["candidate", "active", "retired", "rejected"]
    gates_passed: bool
    created_at: dt.datetime
    activated_at: dt.datetime | None = None
    metrics: dict[str, Any]
    loaded: bool = False


class Holdout(BaseModel):
    mae: float | None = None
    rmse: float | None = None
    coverage_80: float | None = None
    mean_width_80: float | None = None


class Importance(BaseModel):
    feature: str
    mean_abs_shap: float | None


class GateSummary(BaseModel):
    name: str
    passed: bool
    required: bool
    message: str | None = None


class CardSections(BaseModel):
    intended_use: str | None = None
    limitations: list[str] = []
    features: list[str] = []
    run_id: str | None = None
    trained_at: str | None = None
    gates: list[GateSummary] = []


class ModelCardView(BaseModel):
    version: str
    feature_set: Literal["full", "core"]
    status: Literal["candidate", "active", "retired", "rejected"]
    gates_passed: bool
    created_at: dt.datetime | None = None
    activated_at: dt.datetime | None = None
    activated_by_role: Literal["platform_admin", "cli"] | None = None
    datasets: list[str] = []
    thresholds: list[float] | None = None
    thresholds_source: str
    holdout: Holdout
    feature_sets: dict[str, Holdout] = {}
    baselines: dict[str, float | None] = {}
    shap_global: list[Importance] = []
    card: CardSections


class DailyError(BaseModel):
    date: dt.date
    p10: float
    p50: float
    p90: float
    actual: float
    error: float = Field(description="actual minus p50, hours")
    covered: bool
    predicted_class: str | None = None


class HistBin(BaseModel):
    start: float
    end: float
    count: int


class Confusion(BaseModel):
    labels: list[str]
    matrix: list[list[int]] = Field(description="rows: actual class, columns: predicted class")
    days: int


class LiveMetrics(BaseModel):
    window_days: int
    days: int
    mae: float | None = None
    rmse: float | None = None
    coverage_80: float | None = None
    coverage_target: float = 0.8
    bias: float | None = Field(default=None, description="mean of actual minus p50, hours")
    daily: list[DailyError] = []
    residual_histogram: list[HistBin] = []
    confusion: Confusion | None = None


class Performance(BaseModel):
    department_id: str
    active: list[ModelCardView]
    live: LiveMetrics
    registry: list[ModelCardView] | None = Field(
        default=None, description="Every version, for platform admins only"
    )


class RollbackBody(BaseModel):
    feature_set: Literal["full", "core"] = "full"


class Reloaded(BaseModel):
    changed: bool
    versions: dict[str, str]


def get_model_service(request: Request) -> ModelService:
    service: ModelService = request.app.state.model_service
    return service


@router.get("", response_model=list[ModelVersionOut])
async def list_models(
    access: GlobalAccess = Depends(READ),
    gw: Gateway = Depends(get_gateway),
    service: ModelService = Depends(get_model_service),
) -> list[ModelVersionOut]:
    """Registered versions with metrics and status, newest first (RLS applies)."""
    rows = await gw.select(
        access.principal.token,
        "model_versions",
        {
            "select": "version,feature_set,status,gates_passed,created_at,activated_at,metrics",
            "order": "created_at.desc",
        },
    )
    log.info("model_registry_viewed", user_id=access.principal.user_id, rows=len(rows))
    loaded = set(service.versions().values())
    return [ModelVersionOut(**r, loaded=r["version"] in loaded) for r in rows]


@router.post("/{version}/activate", response_model=ModelVersionOut)
async def activate_model(
    version: str,
    access: GlobalAccess = Depends(ADMIN),
    settings: Settings = Depends(get_settings),
    service: ModelService = Depends(get_model_service),
) -> ModelVersionOut:
    """Platform admin only, with a fresh two-factor proof. Refused unless the version passed its
    activation gates. The previous active version of the feature set is retired; the change is
    written to audit_log by the table trigger, and this API instance swaps in the new model."""
    check_recent_totp(access.principal)
    resp = await ServiceClient(settings).rpc_response(
        "activate_model_version", {"p_version": version, "p_actor": access.principal.user_id}
    )
    if resp.status_code >= 400:
        code = (resp.json() or {}).get("code") if resp.content else None
        if code == "23514":
            raise ApiError(
                409, "this version has not passed its activation gates", GATES_NOT_PASSED
            )
        if code == "P0002":
            raise ApiError(404, "model version not found")
        raise ApiError(502, "activation failed")
    row = resp.json()
    log.info("model_activated", user_id=access.principal.user_id, version=version)
    await service.refresh()
    return ModelVersionOut(**row, loaded=version in service.versions().values())


@router.get("/performance", response_model=Performance)
async def performance(
    department_id: str = Query(..., pattern=UUID_PATTERN),
    window: int = Query(30, ge=7, le=365, description="Days of real data to score"),
    access: DepartmentAccess = Depends(PERF),
    gw: Gateway = Depends(get_gateway),
) -> Performance:
    """Holdout metrics of the active models and live accuracy on approved real shift logs."""
    token = access.principal.token
    _, tz = await plan_svc.department(gw, token, access.department_id)
    since = perf.window_start(plan_svc.today_in(tz), window).isoformat()
    cols = (
        "version,feature_set,status,gates_passed,created_at,activated_at,activated_by,metrics,card"
    )
    registry = await gw.select(
        token, "model_versions", {"select": cols, "order": "created_at.desc"}
    )
    forecasts = await gw.select(
        token,
        "forecasts",
        {
            "select": "target_date,ot_p10,ot_p50,ot_p90,burden_class,thresholds,created_at",
            "department_id": f"eq.{access.department_id}",
            "target_date": f"gte.{since}",
            "order": "target_date.asc",
        },
    )
    actuals = await gw.select(
        token,
        "shift_actuals",
        {
            "select": "shift_date,ot_labor_hours,source,status",
            "department_id": f"eq.{access.department_id}",
            "source": "eq.real",
            "status": "eq.approved",
            "shift_date": f"gte.{since}",
        },
    )
    views = [ModelCardView(**perf.card_view(r)) for r in registry]
    return Performance(
        department_id=access.department_id,
        active=[v for v in views if v.status == "active"],
        live=LiveMetrics(**perf.live_metrics(forecasts, actuals, window)),
        registry=views if "platform_admin" in access.roles else None,
    )


@router.post("/rollback", response_model=ModelVersionOut)
async def rollback_model(
    body: RollbackBody,
    access: GlobalAccess = Depends(ADMIN),
    settings: Settings = Depends(get_settings),
    service: ModelService = Depends(get_model_service),
) -> ModelVersionOut:
    """Platform admin with a fresh two-factor proof: re-activate the most recently retired
    version of the feature set. Audited by the model_versions trigger."""
    check_recent_totp(access.principal)
    resp = await ServiceClient(settings).rpc_response(
        "rollback_model_version",
        {"p_feature_set": body.feature_set, "p_actor": access.principal.user_id},
    )
    if resp.status_code >= 400:
        code = (resp.json() or {}).get("code") if resp.content else None
        if code == "P0002":
            raise ApiError(409, "there is no earlier version to roll back to")
        raise ApiError(502, "rollback failed")
    row = resp.json()
    log.info("model_rolled_back", user_id=access.principal.user_id, version=row.get("version"))
    await service.refresh()
    return ModelVersionOut(**row, loaded=row["version"] in service.versions().values())


@internal.post("/models/reload", response_model=Reloaded)
async def reload_models(
    x_internal_token: str = Header(default=""),
    settings: Settings = Depends(get_settings),
    service: ModelService = Depends(get_model_service),
) -> Reloaded:
    """Force a check for newly activated models (used by deploy and sg ml activate)."""
    if not settings.internal_token or not hmac.compare_digest(
        x_internal_token.encode(), settings.internal_token.encode()
    ):
        raise ApiError(404, "not found")
    changed = await service.refresh()
    return Reloaded(changed=changed, versions=service.versions())
