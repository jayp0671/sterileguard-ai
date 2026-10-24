"""Rate limits (SG-11, plan §7.2), keyed by user id with IP fallback.

Default 120 requests per minute. Heavier routes get tighter limits by path prefix:
forecasts (POST) and scenarios 30 per minute, agents 10 per minute. Over the limit the API
returns 429 problem+json with Retry-After. Built directly on `limits` (moving window, in
memory): the API runs as one Hugging Face Space instance on the free tier. slowapi was tried
first, but its middleware cannot see routes inside included routers on this FastAPI version.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

from limits import RateLimitItem, parse
from limits.storage import MemoryStorage
from limits.strategies import MovingWindowRateLimiter
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from sg_api.core.auth import bearer_token, get_verifier
from sg_api.core.config import get_settings
from sg_api.core.errors import ApiError, problem_response
from sg_api.core.idempotency import resolve_dependency as _resolve

DEFAULT_LIMIT = "120/minute"
RATE_LIMITED = "https://sterileguard.dev/problems/rate-limited"


@dataclass(frozen=True)
class Rule:
    prefix: str
    limit: str
    methods: frozenset[str] = frozenset()  # empty: every method

    def applies(self, method: str, path: str) -> bool:
        return path.startswith(self.prefix) and (not self.methods or method in self.methods)


RULES: tuple[Rule, ...] = (
    Rule("/v1/forecasts", "30/minute", frozenset({"POST"})),
    Rule("/v1/scenarios", "30/minute"),
    Rule("/v1/agents/", "10/minute"),
)

_storage = MemoryStorage()
_window = MovingWindowRateLimiter(_storage)


def reset() -> None:
    _storage.reset()


def rate_key(request: Request) -> str:
    """The verified user id, else the client IP. Only a token that verifies picks a user bucket,
    so a forged token cannot use up someone else's limit (signing keys are cached 10 minutes)."""
    token = bearer_token(request)
    if token:
        try:
            settings = _resolve(request, get_settings)
            return f"user:{_resolve(request, get_verifier, settings).verify(token).user_id}"
        except ApiError:
            pass
    host = request.client.host if request.client else "unknown"
    return f"ip:{host}"


def limit_for(method: str, path: str) -> tuple[str, RateLimitItem]:
    for rule in RULES:
        if rule.applies(method, path):
            return rule.prefix, parse(rule.limit)
    return "default", parse(DEFAULT_LIMIT)


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        scope, item = limit_for(request.method, request.url.path)
        key = rate_key(request)
        if not _window.hit(item, scope, key):
            stats = _window.get_window_stats(item, scope, key)
            retry = max(1, math.ceil(stats.reset_time - time.time()))
            return problem_response(
                request,
                429,
                f"too many requests (limit {item}); try again in {retry} s",
                type_=RATE_LIMITED,
                headers={"Retry-After": str(retry), "X-RateLimit-Limit": str(item.amount)},
            )
        response = await call_next(request)
        stats = _window.get_window_stats(item, scope, key)
        response.headers["X-RateLimit-Limit"] = str(item.amount)
        response.headers["X-RateLimit-Remaining"] = str(stats.remaining)
        return response
