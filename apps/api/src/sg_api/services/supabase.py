"""Thin Supabase gateway over PostgREST and the Auth admin API.

Business queries run with the caller's access token so RLS applies (plan §7.1, least privilege).
The service-role key is used only through sg_api.db.service_client (invite emails).
"""

from __future__ import annotations

from typing import Any, Protocol

import httpx

from sg_api.core.config import Settings
from sg_api.core.errors import ApiError
from sg_api.core.middleware import HEADER, REQUEST_ID
from sg_api.db.service_client import ServiceClient

Row = dict[str, Any]


class Gateway(Protocol):
    async def select(self, token: str, table: str, params: dict[str, str]) -> list[Row]: ...
    async def insert(self, token: str, table: str, row: Row) -> Row: ...
    async def insert_many(self, token: str, table: str, rows: list[Row]) -> list[Row]: ...
    async def update(
        self, token: str, table: str, params: dict[str, str], patch: Row
    ) -> list[Row]: ...
    async def rpc(self, token: str, fn: str, args: Row | None = None) -> Any: ...
    async def upsert(self, token: str, table: str, row: Row, on_conflict: str) -> Row: ...
    async def admin_invite(self, email: str, redirect_to: str) -> None: ...


class SupabaseGateway:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self.base = settings.supabase_url.rstrip("/")
        self.client = client or httpx.AsyncClient(timeout=10.0)

    def _headers(self, token: str) -> dict[str, str]:
        headers = {
            "apikey": self.settings.supabase_anon_key,
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        # PostgREST exposes request headers to SQL; the audit trigger reads x-request-id.
        if request_id := REQUEST_ID.get():
            headers[HEADER] = request_id
        return headers

    @staticmethod
    def _raise(resp: httpx.Response) -> None:
        if resp.status_code < 400:
            return
        if resp.status_code in (401, 403):
            raise ApiError(403, "not allowed")
        if resp.status_code == 409:
            raise ApiError(409, "conflict")
        if resp.status_code < 500:
            raise ApiError(422, "request rejected by the database")
        raise ApiError(502, "database error")

    async def select(self, token: str, table: str, params: dict[str, str]) -> list[Row]:
        resp = await self.client.get(
            f"{self.base}/rest/v1/{table}", params=params, headers=self._headers(token)
        )
        self._raise(resp)
        rows: list[Row] = resp.json()
        return rows

    async def insert(self, token: str, table: str, row: Row) -> Row:
        headers = {**self._headers(token), "Prefer": "return=representation"}
        resp = await self.client.post(f"{self.base}/rest/v1/{table}", json=row, headers=headers)
        self._raise(resp)
        rows: list[Row] = resp.json()
        return rows[0]

    async def insert_many(self, token: str, table: str, rows: list[Row]) -> list[Row]:
        """One request for many rows (PostgREST accepts a JSON array)."""
        if not rows:
            return []
        headers = {**self._headers(token), "Prefer": "return=representation"}
        resp = await self.client.post(f"{self.base}/rest/v1/{table}", json=rows, headers=headers)
        self._raise(resp)
        out: list[Row] = resp.json()
        return out

    async def update(self, token: str, table: str, params: dict[str, str], patch: Row) -> list[Row]:
        headers = {**self._headers(token), "Prefer": "return=representation"}
        resp = await self.client.patch(
            f"{self.base}/rest/v1/{table}", params=params, json=patch, headers=headers
        )
        self._raise(resp)
        rows: list[Row] = resp.json()
        return rows

    async def upsert(self, token: str, table: str, row: Row, on_conflict: str) -> Row:
        headers = {
            **self._headers(token),
            "Prefer": "resolution=merge-duplicates,return=representation",
        }
        resp = await self.client.post(
            f"{self.base}/rest/v1/{table}",
            params={"on_conflict": on_conflict},
            json=row,
            headers=headers,
        )
        self._raise(resp)
        rows: list[Row] = resp.json()
        return rows[0]

    async def rpc(self, token: str, fn: str, args: Row | None = None) -> Any:
        resp = await self.client.post(
            f"{self.base}/rest/v1/rpc/{fn}", json=args or {}, headers=self._headers(token)
        )
        self._raise(resp)
        return resp.json()

    async def admin_invite(self, email: str, redirect_to: str) -> None:
        # Invite emails need the Auth admin API, which only the service role can call.
        await ServiceClient(self.settings, self.client).admin_invite(email, redirect_to)
