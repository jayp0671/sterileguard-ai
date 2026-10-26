"""FastAPI application factory: `uvicorn sg_api.main:create_app --factory`."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from sg_api import __version__
from sg_api.core.config import Settings, get_settings
from sg_api.core.errors import PROBLEM_JSON, Problem, install_error_handlers
from sg_api.core.idempotency import IdempotencyMiddleware
from sg_api.core.logging import configure_logging
from sg_api.core.middleware import HEADER, RequestIdMiddleware
from sg_api.core.ratelimit import RateLimitMiddleware
from sg_api.db.service_client import ServiceClient
from sg_api.routers import admin, audit, forecasts, health, me, models, plans
from sg_api.services.models import ModelService, SupabaseModelSource

v1 = APIRouter(prefix="/v1")
v1.include_router(admin.router)
v1.include_router(audit.router)
v1.include_router(forecasts.router)
v1.include_router(me.router)
v1.include_router(models.router)
v1.include_router(models.internal)
v1.include_router(plans.router)

# Every route documents the problem+json error shape so clients get a typed ApiError.
ERRORS: dict[int | str, dict[str, object]] = {
    "default": {"model": Problem, "content": {PROBLEM_JSON: {}}, "description": "Problem"}
}


def model_service_for(settings: Settings) -> ModelService:
    """Loads models with the service role when it is configured; otherwise no model (tests,
    local runs without Supabase) and /ready reports it."""
    if not settings.supabase_service_role_key:
        return ModelService(source=None)
    return ModelService(SupabaseModelSource(ServiceClient(settings), settings.model_bucket))


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        service: ModelService = app.state.model_service
        await service.refresh()
        service.start()
        yield
        await service.stop()

    app = FastAPI(
        title="SterileGuard AI API",
        version=__version__,
        description="Decision support only. Academic prototype. No patient data.",
        lifespan=lifespan,
    )
    app.state.model_service = model_service_for(settings)
    # add_middleware wraps: the last one added runs first. Idempotency sits inside GZip so it
    # stores plain JSON; rate limiting runs after request ids are bound.
    app.add_middleware(IdempotencyMiddleware)
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=settings.cors_origin_regex,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type", HEADER, "Idempotency-Key"],
        expose_headers=[HEADER],
    )
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(RequestIdMiddleware)
    install_error_handlers(app)
    app.include_router(health.router, responses=ERRORS)
    app.include_router(v1, responses=ERRORS)
    return app
