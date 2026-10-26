"""Service-role client (SG-11). READ THIS BEFORE USING IT.

The service-role key BYPASSES ROW-LEVEL SECURITY. It exists only for work that no single user's
token can do: sending invite emails through the Auth admin API, scheduled jobs (purging
expired idempotency keys, simulation uploads), loading the active model from the private
`models` bucket (SG-14), and the model status functions, which no user role may call. Never
call it from a request handler on behalf of a user for business data: use
sg_api.db.user_client so RLS applies.
"""

from __future__ import annotations

from typing import Any

import httpx

from sg_api.core.config import Settings
from sg_api.core.errors import ApiError


class ServiceClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.base = settings.supabase_url.rstrip("/")
        self.key = settings.supabase_service_role_key
        self.client = client or httpx.AsyncClient(timeout=10.0)

    def _headers(self) -> dict[str, str]:
        if not self.key:
            raise ApiError(503, "service role key is not configured")
        return {"apikey": self.key, "Authorization": f"Bearer {self.key}"}

    async def admin_invite(self, email: str, redirect_to: str) -> None:
        if not self.key:
            raise ApiError(503, "invite email is not configured (service role key missing)")
        resp = await self.client.post(
            f"{self.base}/auth/v1/invite",
            params={"redirect_to": redirect_to},
            json={"email": email},
            headers=self._headers(),
        )
        if resp.status_code == 422:
            raise ApiError(409, "this email already has an account; ask them to sign in")
        if resp.status_code >= 400:
            raise ApiError(502, "invite email could not be sent")

    async def rpc(self, fn: str, args: dict[str, Any] | None = None) -> Any:
        resp = await self.rpc_response(fn, args)
        if resp.status_code >= 400:
            raise ApiError(502, f"service rpc {fn} failed")
        return resp.json()

    async def rpc_response(self, fn: str, args: dict[str, Any] | None = None) -> httpx.Response:
        """The raw response, for callers that map database error codes themselves."""
        return await self.client.post(
            f"{self.base}/rest/v1/rpc/{fn}", json=args or {}, headers=self._headers()
        )

    async def select(self, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        resp = await self.client.get(
            f"{self.base}/rest/v1/{table}", params=params, headers=self._headers()
        )
        if resp.status_code >= 400:
            raise ApiError(502, f"service select on {table} failed")
        rows: list[dict[str, Any]] = resp.json()
        return rows

    async def download(self, bucket: str, path: str) -> bytes:
        """An object from a private Storage bucket."""
        resp = await self.client.get(
            f"{self.base}/storage/v1/object/{bucket}/{path}", headers=self._headers(), timeout=120.0
        )
        if resp.status_code >= 400:
            raise ApiError(502, f"storage download of {path} failed")
        return resp.content
