"""sg demo helpers (SG-16). No network: only the pure helpers and the safety guard."""

from __future__ import annotations

import base64

import pytest
import typer

from sg_cli.commands import demo


def test_totp_matches_rfc6238_vector() -> None:
    # RFC 6238 appendix B, SHA-1, T = 59 s -> 94287082 (8 digits).
    secret = base64.b32encode(b"12345678901234567890").decode()
    assert demo.totp(secret, at=59, digits=8) == "94287082"
    assert demo.totp(secret, at=1111111109, digits=8) == "07081804"


def test_plus_address() -> None:
    assert demo.plus_address("team@example.edu", "dept_admin") == "team+dept-admin@example.edu"
    with pytest.raises(typer.BadParameter):
        demo.plus_address("not-an-email", "supervisor")


def test_prod_needs_the_explicit_flag() -> None:
    with pytest.raises(SystemExit, match="allow-prod-demo"):
        demo.target("prod", allow_prod=False)
    with pytest.raises(typer.BadParameter):
        demo.target("dev", allow_prod=False)
