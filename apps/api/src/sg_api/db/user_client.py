"""The request-path database client (SG-11, plan §7.1).

Every query a request makes goes to PostgREST with `Authorization: Bearer <user token>` and
`apikey: <anon key>`, so Postgres row-level security decides what the caller can see and change.
The request id is forwarded as X-Request-ID so the audit trigger (SG-08) records it.
"""

from __future__ import annotations

from sg_api.services.supabase import Gateway, Row, SupabaseGateway

UserClient = SupabaseGateway

__all__ = ["Gateway", "Row", "UserClient"]
