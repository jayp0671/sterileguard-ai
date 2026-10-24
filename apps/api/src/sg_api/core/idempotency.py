"""Idempotency-Key handling for POST, PUT and PATCH (SG-11, plan §7.2).

- Same user, same key, same method + path + body within 24 h: the stored response is replayed
  (header `Idempotent-Replayed: true`) and the handler does not run again.
- Same key with a different body: 409 `idempotency_key_reused`.
- Keys live in public.idempotency_keys (migration 0006), written with the caller's own token,
  so RLS keeps each user's keys private. Responses with status >= 500 are not stored.
Requests without the header, or without a valid bearer token, pass through untouched (the
route itself returns 401).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from sg_api.core.auth import bearer_token, get_verifier
from sg_api.core.config import get_settings
from sg_api.core.errors import ApiError, problem_response
from sg_api.core.logging import get_logger

HEADER = "Idempotency-Key"
METHODS = {"POST", "PUT", "PATCH"}
TTL = timedelta(hours=24)
KEY_REUSED = "https://sterileguard.dev/problems/idempotency-key-reused"


def body_hash(method: str, path: str, body: bytes) -> str:
    return hashlib.sha256(method.encode() + b" " + path.encode() + b"\n" + body).hexdigest()


def resolve_dependency(request: Request, dep: Callable[..., Any], *args: Any) -> Any:
    """Use FastAPI dependency overrides when present (tests), else build the dependency."""
    override = request.app.dependency_overrides.get(dep)
    return override() if override else dep(*args)


def _fresh(row: dict[str, Any], now: datetime) -> bool:
    created = datetime.fromisoformat(str(row["created_at"]).replace("Z", "+00:00"))
    return now - created < TTL


class IdempotencyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        key = request.headers.get(HEADER)
        token = bearer_token(request)
        if request.method not in METHODS or not key or not token:
            return await call_next(request)
        if len(key) > 200:
            return problem_response(request, 400, "Idempotency-Key is longer than 200 characters")

        from sg_api.deps import get_gateway  # local: deps imports routers' dependencies

        settings = resolve_dependency(request, get_settings)
        try:
            principal = resolve_dependency(request, get_verifier, settings).verify(token)
        except ApiError:
            return await call_next(request)
        gw = resolve_dependency(request, get_gateway, settings)

        digest = body_hash(request.method, request.url.path, await request.body())
        rows = await gw.select(
            principal.token,
            "idempotency_keys",
            {"select": "*", "user_id": f"eq.{principal.user_id}", "key": f"eq.{key}"},
        )
        now = datetime.now(UTC)
        if rows and _fresh(rows[0], now):
            stored = rows[0]
            if stored["body_hash"] != digest:
                return problem_response(
                    request,
                    409,
                    "this Idempotency-Key was already used with a different request",
                    type_=KEY_REUSED,
                )
            return JSONResponse(
                stored["response"],
                status_code=int(stored["status"]),
                headers={"Idempotent-Replayed": "true"},
            )

        response = await call_next(request)
        if response.status_code >= 500:
            return response
        chunks = [chunk async for chunk in response.body_iterator]  # type: ignore[attr-defined]
        raw = b"".join(c if isinstance(c, bytes) else c.encode() for c in chunks)
        try:
            payload = json.loads(raw or b"null")
        except ValueError:
            payload = None
        if payload is not None:
            try:
                await gw.upsert(
                    principal.token,
                    "idempotency_keys",
                    {
                        "user_id": principal.user_id,
                        "key": key,
                        "method": request.method,
                        "path": request.url.path,
                        "body_hash": digest,
                        "status": response.status_code,
                        "response": payload,
                        "created_at": now.isoformat(),
                    },
                    on_conflict="user_id,key",
                )
            except ApiError as exc:  # never fail the request because the key could not be saved
                get_logger("sg_api.idempotency").warning("idempotency_store_failed", error=str(exc))
        headers = {k: v for k, v in response.headers.items() if k.lower() != "content-length"}
        return Response(
            raw, status_code=response.status_code, headers=headers, media_type=response.media_type
        )
