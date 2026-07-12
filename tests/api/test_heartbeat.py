"""Tests for the heartbeat receiver API endpoint."""

from datetime import UTC, datetime

from httpx import AsyncClient


def _node_payload(node_id: str = "node-001") -> dict:
    """Build a valid node registration payload."""
    return {
        "node_id": node_id,
        "hostname": f"host-{node_id}",
        "ip_address": "10.0.0.1",
        "region": "us-east-1",
        "gpu": {
            "name": "NVIDIA A100",
            "vram_total_gb": 80.0,
            "vram_available_gb": 60.0,
        },
        "cpu_cores": 32,
        "ram_total_gb": 128.0,
        "available_models": ["llama-3-70b"],
    }


def _heartbeat_payload(node_id: str = "node-001", queue_length: int = 0) -> dict:
    """Build a valid heartbeat payload."""
    return {
        "node_id": node_id,
        "timestamp": datetime.now(tz=UTC).isoformat(),
        "status": "online",
        "queue_length": queue_length,
        "cpu_utilization": 15.5,
        "ram_available_gb": 96.0,
        "gpu_utilization": 45.0,
        "vram_available_gb": 48.0,
    }


class TestHeartbeatAPI:
    """Tests for POST /heartbeat."""

    async def test_heartbeat_success(self, client: AsyncClient):
        # Register a node first
        reg_response = await client.post("/nodes/register", json=_node_payload("node-1"))
        assert reg_response.status_code == 201

        # Send heartbeat
        hb_payload = _heartbeat_payload("node-1", queue_length=3)
        response = await client.post("/heartbeat", json=hb_payload)
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

        # Fetch the node to check registration is still ok
        node_response = await client.get("/nodes/node-1")
        assert node_response.status_code == 200
        assert node_response.json()["node_id"] == "node-1"

    async def test_heartbeat_unknown_node_returns_404(self, client: AsyncClient):
        hb_payload = _heartbeat_payload("unknown-node")
        response = await client.post("/heartbeat", json=hb_payload)
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    async def test_heartbeat_invalid_payload_returns_422(self, client: AsyncClient):
        # Missing required fields
        response = await client.post("/heartbeat", json={"node_id": "node-1"})
        assert response.status_code == 422
