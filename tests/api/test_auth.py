"""Tests for security token authentication."""

from httpx import ASGITransport, AsyncClient

from scheduler.core.config import Settings, get_settings
from scheduler.main import create_app


def _make_unauthorized_client() -> AsyncClient:
    app = create_app()
    settings = Settings(
        environment="development",
        debug=True,
        log_level="debug",
        network_auth_token="test-auth-token",
    )
    app.dependency_overrides[get_settings] = lambda: settings
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


class TestAuthenticationEnforcement:
    """Verify that protected API endpoints enforce X-Network-Auth-Token."""

    async def test_register_node_unauthorized_missing_token(self):
        async with _make_unauthorized_client() as clean_client:
            response = await clean_client.post(
                "/nodes/register",
                json={
                    "node_id": "test-node",
                    "hostname": "test-host",
                    "ip_address": "127.0.0.1",
                    "region": "us-east-1",
                    "gpu": {
                        "name": "NVIDIA A10G",
                        "vram_total_gb": 24.0,
                        "vram_available_gb": 24.0,
                    },
                    "cpu_cores": 8,
                    "ram_total_gb": 32.0,
                    "available_models": ["llama-3"],
                },
            )
        assert response.status_code == 401
        assert response.json()["detail"] == "Unauthorized"

    async def test_register_node_unauthorized_invalid_token(self):
        async with _make_unauthorized_client() as clean_client:
            response = await clean_client.post(
                "/nodes/register",
                json={},
                headers={"X-Network-Auth-Token": "bad-token"},
            )
        assert response.status_code == 401

    async def test_heartbeat_unauthorized_missing_token(self):
        async with _make_unauthorized_client() as clean_client:
            response = await clean_client.post(
                "/heartbeat",
                json={
                    "node_id": "test-node",
                    "timestamp": "2026-07-16T12:00:00Z",
                    "status": "online",
                    "queue_length": 0,
                    "cpu_utilization": 0.0,
                    "ram_available_gb": 32.0,
                    "gpu_utilization": 0.0,
                    "vram_available_gb": 24.0,
                },
            )
        assert response.status_code == 401

    async def test_heartbeat_unauthorized_invalid_token(self):
        async with _make_unauthorized_client() as clean_client:
            response = await clean_client.post(
                "/heartbeat",
                json={},
                headers={"X-Network-Auth-Token": "bad-token"},
            )
        assert response.status_code == 401

    async def test_schedule_unauthorized_missing_token(self):
        async with _make_unauthorized_client() as clean_client:
            response = await clean_client.post(
                "/schedule",
                json={"model_name": "llama-3"},
            )
        assert response.status_code == 401

    async def test_schedule_unauthorized_invalid_token(self):
        async with _make_unauthorized_client() as clean_client:
            response = await clean_client.post(
                "/schedule",
                json={"model_name": "llama-3"},
                headers={"X-Network-Auth-Token": "bad-token"},
            )
        assert response.status_code == 401
