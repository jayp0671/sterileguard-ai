"""Request ID middleware: read X-Request-ID or make a UUID4, bind it to logs, echo it back."""

from __future__ import annotations

import re
import time
import uuid
from contextvars import ContextVar

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from sg_api.core.logging import get_logger

HEADER = "X-Request-ID"
# The current request id, forwarded to PostgREST so the audit trigger records it (SG-11).
REQUEST_ID: ContextVar[str | None] = ContextVar("request_id", default=None)
_SAFE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming = request.headers.get(HEADER, "")
        request_id = incoming if _SAFE.match(incoming) else str(uuid.uuid4())
        request.state.request_id = request_id
        token = REQUEST_ID.set(request_id)
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            REQUEST_ID.reset(token)
        response.headers[HEADER] = request_id
        get_logger().info(
            "request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round((time.perf_counter() - start) * 1000, 1),
        )
        return response
