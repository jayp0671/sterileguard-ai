"""Supabase access-token verification (JWKS) and the auth dependencies every route uses.

Plan §7.1 and §9: verify the token against the project's published signing keys, require aal2
(two-factor) for business data, enforce the 12-hour absolute session limit server-side, and
require a TOTP verification within the last 5 minutes for sensitive actions.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import jwt
from fastapi import Depends, Request
from jwt import PyJWKClient

from sg_api.core.config import Settings, get_settings
from sg_api.core.errors import ApiError

ALGORITHMS = ["ES256", "RS256", "EdDSA"]
SESSION_LIMIT_S = 12 * 3600
REAUTH_WINDOW_S = 5 * 60
JWKS_CACHE_S = 10 * 60
MFA_REQUIRED = "https://sterileguard.dev/problems/mfa-required"


@dataclass(frozen=True)
class Principal:
    """The verified caller. `token` is forwarded to Supabase so RLS applies."""

    user_id: str
    token: str
    email: str | None = None
    aal: str = "aal1"
    session_id: str | None = None
    amr: list[dict[str, Any]] = field(default_factory=list)

    @property
    def is_aal2(self) -> bool:
        return self.aal == "aal2"

    def last_totp_at(self) -> int | None:
        times = [int(e.get("timestamp", 0)) for e in self.amr if e.get("method") == "totp"]
        return max(times) if times else None


class TokenVerifier:
    def __init__(self, settings: Settings, jwks_client: PyJWKClient | None = None) -> None:
        self.issuer = f"{settings.supabase_url.rstrip('/')}/auth/v1"
        self.jwks = jwks_client or PyJWKClient(
            settings.supabase_jwks_url, cache_keys=True, cache_jwk_set=True, lifespan=JWKS_CACHE_S
        )

    def verify(self, token: str) -> Principal:
        try:
            key = self.jwks.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                key.key,
                algorithms=ALGORITHMS,
                audience="authenticated",
                issuer=self.issuer,
                options={"require": ["exp", "sub", "aud"]},
            )
        except (jwt.PyJWTError, jwt.PyJWKClientError) as exc:
            raise ApiError(401, f"invalid access token: {type(exc).__name__}") from exc
        return Principal(
            user_id=str(claims["sub"]),
            token=token,
            email=claims.get("email"),
            aal=str(claims.get("aal", "aal1")),
            session_id=claims.get("session_id"),
            amr=list(claims.get("amr") or []),
        )


@lru_cache
def _verifier(settings: Settings) -> TokenVerifier:
    return TokenVerifier(settings)


def get_verifier(settings: Settings = Depends(get_settings)) -> TokenVerifier:
    return _verifier(settings)


def bearer_token(request: Request) -> str | None:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token.strip() else None


def get_principal(request: Request, verifier: TokenVerifier = Depends(get_verifier)) -> Principal:
    token = bearer_token(request)
    if token is None:
        raise ApiError(401, "missing bearer token")
    return verifier.verify(token)


def optional_principal(
    request: Request, verifier: TokenVerifier = Depends(get_verifier)
) -> Principal | None:
    token = bearer_token(request)
    if token is None:
        return None
    try:
        return verifier.verify(token)
    except ApiError:
        return None


def require_aal2(principal: Principal = Depends(get_principal)) -> Principal:
    if not principal.is_aal2:
        raise ApiError(403, "two-factor authentication required (aal2)", type_=MFA_REQUIRED)
    return principal


def check_recent_totp(principal: Principal, now: float | None = None) -> None:
    """Sensitive actions need a TOTP verification in the last 5 minutes (JWT amr claim)."""
    last = principal.last_totp_at()
    if last is None or (now or time.time()) - last > REAUTH_WINDOW_S:
        raise ApiError(
            401,
            "re-authentication required: verify a fresh two-factor code",
            type_="https://sterileguard.dev/problems/reauth-required",
        )


def require_recent_totp(principal: Principal = Depends(require_aal2)) -> Principal:
    check_recent_totp(principal)
    return principal


def check_session_age(age_s: int | None) -> None:
    """age_s comes from public.session_age_seconds(); None means the session was signed out."""
    if age_s is None:
        raise ApiError(401, "session ended; sign in again")
    if age_s > SESSION_LIMIT_S:
        raise ApiError(401, "session expired (12 hour limit); sign in again")
