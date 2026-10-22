from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, EmailStr


class AppRole(StrEnum):
    technician = "technician"
    supervisor = "supervisor"
    dept_admin = "dept_admin"
    data_steward = "data_steward"
    platform_admin = "platform_admin"


class InviteCreate(BaseModel):
    email: EmailStr
    department_id: UUID
    role: AppRole


class Invite(BaseModel):
    id: UUID
    email: str
    department_id: UUID
    role: AppRole
    created_at: datetime
    expires_at: datetime
    accepted_at: datetime | None = None
    revoked_at: datetime | None = None
