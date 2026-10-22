"""Auth event audit (SG-04). Until SG-08 adds audit_log, events are only logged as JSON.
No email addresses or IPs are logged: the user is identified by id only."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from sg_api.core.auth import Principal, optional_principal
from sg_api.core.logging import get_logger

router = APIRouter(prefix="/audit", tags=["audit"])

AuthEventName = Literal[
    "sign_in_success",
    "sign_in_failure",
    "mfa_enroll",
    "mfa_unenroll",
    "mfa_challenge_failure",
    "sign_out",
    "sign_out_global",
    "idle_timeout",
    "session_expired",
]


class AuthEvent(BaseModel):
    event: AuthEventName


class Accepted(BaseModel):
    status: Literal["accepted"] = "accepted"


@router.post("/auth-event", response_model=Accepted, status_code=202)
async def auth_event(
    body: AuthEvent, principal: Principal | None = Depends(optional_principal)
) -> Accepted:
    get_logger("sg_api.audit").info(
        "auth_event",
        auth_event=body.event,
        user_id=principal.user_id if principal else None,
        aal=principal.aal if principal else None,
    )
    return Accepted()
