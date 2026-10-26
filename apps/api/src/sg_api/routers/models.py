"""Model registry endpoints (SG-14, plan §7.2, §12.7)."""

from __future__ import annotations

import datetime as dt
import hmac
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel

from sg_api.core.auth import check_recent_totp
from sg_api.core.config import Settings, get_settings
from sg_api.core.errors import ApiError
from sg_api.core.logging import get_logger
from sg_api.core.roles import GlobalAccess, require_any_role
from sg_api.db.service_client import ServiceClient
from sg_api.deps import get_gateway
from sg_api.services.models import ModelService
from sg_api.services.supabase import Gateway

router = APIRouter(prefix="/models", tags=["models"])
internal = APIRouter(prefix="/internal", tags=["internal"], include_in_schema=False)
log = get_logger("sg_api.audit")

SUPERVISOR_AND_ABOVE = ("supervisor", "dept_admin", "platform_admin")
GATES_NOT_PASSED = "https://sterileguard.dev/problems/gates-not-passed"
READ = require_any_role(*SUPERVISOR_AND_ABOVE)
ADMIN = require_any_role("platform_admin")


class ModelVersionOut(BaseModel):
    version: str
    feature_set: Literal["full", "core"]
    status: Literal["candidate", "active", "retired", "rejected"]
    gates_passed: bool
    created_at: dt.datetime
    activated_at: dt.datetime | None = None
    metrics: dict[str, Any]
    loaded: bool = False


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
