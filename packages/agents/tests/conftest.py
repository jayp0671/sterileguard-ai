"""Fixtures for packages/agents tests. Synthetic data only, fixed seeds, no network.

Every test runs with NIM_MODE=replay and without NIM_API_KEY, and the real transport is
replaced by one that fails the test, so CI can never make a live NIVIDA call."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))


@pytest.fixture(autouse=True)
def _no_live_calls(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    from sg_agents import nim

    async def refuse(self: Any, *a: Any, **k: Any) -> Any:
        raise AssertionError("a test tried to call NVIDIA NIM live")

    monkeypatch.setenv("NIM_MODE", "replay")
    monkeypatch.delenv("NIM_API_KEY", raising=False)
    monkeypatch.setattr(nim.OpenAITransport, "complete", refuse)
    yield
