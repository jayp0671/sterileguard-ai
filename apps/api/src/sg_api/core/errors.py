"""RFC 9457 problem+json errors for every failure, each carrying the request_id."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from sg_api.core.logging import get_logger

PROBLEM_JSON = "application/problem+json"


class FieldError(BaseModel):
    loc: list[str | int]
    msg: str
    type: str


class Problem(BaseModel):
    """Problem Details (RFC 9457)."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    request_id: str | None = None
    errors: list[FieldError] | None = None


class ApiError(Exception):
    """Raise from routes or services to return a problem+json response."""

    def __init__(self, status: int, detail: str, type_: str = "about:blank") -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail
        self.type = type_


def problem_response(
    request: Request,
    status: int,
    detail: str | None = None,
    type_: str = "about:blank",
    errors: list[FieldError] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = Problem(
        type=type_,
        title=HTTPStatus(status).phrase,
        status=status,
        detail=detail,
        request_id=getattr(request.state, "request_id", None),
        errors=errors,
    )
    return JSONResponse(
        body.model_dump(exclude_none=True),
        status_code=status,
        media_type=PROBLEM_JSON,
        headers=headers,
    )


def install_error_handlers(app: FastAPI) -> None:
    log = get_logger()

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            FieldError(loc=list(e.get("loc", [])), msg=str(e.get("msg")), type=str(e.get("type")))
            for e in exc.errors()
        ]
        return problem_response(request, 422, "Request validation failed", errors=errors)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        headers: dict[str, Any] | None = getattr(exc, "headers", None)
        return problem_response(request, exc.status_code, str(exc.detail), headers=headers)

    @app.exception_handler(ApiError)
    async def _api(request: Request, exc: ApiError) -> JSONResponse:
        return problem_response(request, exc.status, exc.detail, type_=exc.type)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_error", path=request.url.path)
        return problem_response(request, 500, "Internal server error")
