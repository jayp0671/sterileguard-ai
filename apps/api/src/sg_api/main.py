"""FastAPI application factory: `uvicorn sg_api.main:create_app --factory`."""

from __future__ import annotations

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from sg_api import __version__
from sg_api.core.config import Settings, get_settings
from sg_api.core.errors import PROBLEM_JSON, Problem, install_error_handlers
from sg_api.core.logging import configure_logging
from sg_api.core.middleware import HEADER, RequestIdMiddleware
from sg_api.routers import admin, audit, health

v1 = APIRouter(prefix="/v1")
v1.include_router(admin.router)
v1.include_router(audit.router)

# Every route documents the problem+json error shape so clients get a typed ApiError.
ERRORS: dict[int | str, dict[str, object]] = {
    "default": {"model": Problem, "content": {PROBLEM_JSON: {}}, "description": "Problem"}
}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging()
    app = FastAPI(
        title="SterileGuard AI API",
        version=__version__,
        description="Decision support only. Academic prototype. No patient data.",
    )
    app.state.model = None
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type", HEADER, "Idempotency-Key"],
        expose_headers=[HEADER],
    )
    app.add_middleware(RequestIdMiddleware)
    install_error_handlers(app)
    app.include_router(health.router, responses=ERRORS)
    app.include_router(v1, responses=ERRORS)
    return app
