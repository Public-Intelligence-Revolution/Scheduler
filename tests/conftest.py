"""Shared test fixtures."""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from scheduler.core.config import Settings, get_settings
from scheduler.main import create_app


@pytest.fixture
def settings() -> Settings:
    """Provide test settings with stable defaults."""
    return Settings(
        environment="development",
        debug=True,
        log_level="debug",
        network_auth_token="test-auth-token",
    )


@pytest.fixture
async def client(settings: Settings) -> AsyncGenerator[AsyncClient, None]:
    """Provide an async HTTP test client."""
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-Network-Auth-Token": "test-auth-token"},
    ) as ac:
        yield ac
