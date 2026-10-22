"""Example polyfactory usage (SG-05): build valid synthetic request models."""

from __future__ import annotations

from polyfactory.factories.pydantic_factory import ModelFactory

from sg_api.schemas.invites import AppRole, InviteCreate


class InviteCreateFactory(ModelFactory[InviteCreate]):
    __random_seed__ = 595
    __check_model__ = True


def test_invite_factory_builds_valid_models() -> None:
    invite = InviteCreateFactory.build(role=AppRole.technician)
    assert invite.role is AppRole.technician
    assert "@" in invite.email
