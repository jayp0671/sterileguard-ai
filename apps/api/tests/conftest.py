from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from sg_api.core.config import Settings, get_settings
from sg_api.main import create_app


@pytest.fixture
def settings() -> Settings:
    return Settings(
        env="test",
        supabase_url="http://db.invalid:54321",
        supabase_anon_key="test-anon",
        git_sha="abcdef1234567890",
        ready_timeout_s=0.5,
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as c:
        yield c
