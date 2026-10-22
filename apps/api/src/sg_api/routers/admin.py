"""Admin endpoints: invites (SG-04). Users, roles and audit arrive in SG-25."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from sg_api.core.auth import Principal
from sg_api.deps import current_user, get_invite_service
from sg_api.schemas.invites import Invite, InviteCreate
from sg_api.services.invites import InviteService

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/invites", response_model=Invite, status_code=201)
async def create_invite(
    body: InviteCreate,
    user: Principal = Depends(current_user),
    svc: InviteService = Depends(get_invite_service),
) -> Invite:
    return Invite.model_validate(await svc.create(user, body))


@router.post("/invites/{invite_id}/resend", response_model=Invite)
async def resend_invite(
    invite_id: UUID,
    user: Principal = Depends(current_user),
    svc: InviteService = Depends(get_invite_service),
) -> Invite:
    return Invite.model_validate(await svc.resend(user, str(invite_id)))


@router.post("/invites/{invite_id}/revoke", response_model=Invite)
async def revoke_invite(
    invite_id: UUID,
    user: Principal = Depends(current_user),
    svc: InviteService = Depends(get_invite_service),
) -> Invite:
    return Invite.model_validate(await svc.revoke(user, str(invite_id)))
