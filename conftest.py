"""Shared pytest setup for every Python member (repo-root conftest)."""

from __future__ import annotations

import os

from hypothesis import HealthCheck, settings

# HYPOTHESIS_PROFILE=ci in CI: fixed, derandomized, 50 examples. dev locally: more examples.
settings.register_profile("ci", max_examples=50, deadline=None, derandomize=True)
settings.register_profile(
    "dev", max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow]
)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))
