"""Liveness (/health) and readiness (/ready)."""

from __future__ import annotations

from typing import Literal

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from sg_api import __version__
from sg_api.core.config import Settings, get_settings

router = APIRouter(tags=["health"])


class Health(BaseModel):
    status: Literal["ok"]
    version: str


class Check(BaseModel):
    ok: bool
    reason: str | None = None


class Ready(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: dict[str, Check]


def app_version(settings: Settings) -> str:
    return settings.git_sha[:12] if settings.git_sha else __version__


async def check_database(settings: Settings) -> Check:
    """Lightweight PostgREST call: the REST root answers when the database is reachable."""
    try:
        async with httpx.AsyncClient(timeout=settings.ready_timeout_s) as client:
            resp = await client.get(
                f"{settings.supabase_url.rstrip('/')}/rest/v1/",
                headers={"apikey": settings.supabase_anon_key},
            )
    except httpx.HTTPError as exc:
        return Check(ok=False, reason=f"database unreachable: {type(exc).__name__}")
    if resp.status_code >= 500:
        return Check(ok=False, reason=f"database returned {resp.status_code}")
    return Check(ok=True)


def check_model(request: Request) -> Check:
    loaded = getattr(request.app.state, "model", None) is not None
    return Check(ok=loaded, reason=None if loaded else "no active model loaded (SG-14)")


@router.get("/health", response_model=Health)
async def health(settings: Settings = Depends(get_settings)) -> Health:
    return Health(status="ok", version=app_version(settings))


@router.get(
    "/ready",
    response_model=Ready,
    responses={503: {"model": Ready, "description": "One or more checks failed"}},
)
async def ready(request: Request, settings: Settings = Depends(get_settings)) -> JSONResponse:
    checks = {"database": await check_database(settings), "model": check_model(request)}
    ok = all(c.ok for c in checks.values())
    body = Ready(status="ready" if ok else "not_ready", checks=checks)
    return JSONResponse(body.model_dump(exclude_none=True), status_code=200 if ok else 503)
