"""Tests for the scheduling / selection API endpoint."""

from datetime import UTC, datetime

from httpx import AsyncClient


def _node_payload(node_id: str = "node-001", models: list[str] | None = None) -> dict:
    """Build a valid node registration payload."""
    if models is None:
        models = ["llama-3"]
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
        "available_models": models,
    }


def _heartbeat_payload(
    node_id: str = "node-001",
    status: str = "online",
    queue_length: int = 0,
    cpu_utilization: float = 0.0,
    gpu_utilization: float = 0.0,
    vram_available_gb: float = 40.0,
) -> dict:
    """Build a valid heartbeat payload."""
    return {
        "node_id": node_id,
        "timestamp": datetime.now(tz=UTC).isoformat(),
        "status": status,
        "queue_length": queue_length,
        "cpu_utilization": cpu_utilization,
        "ram_available_gb": 96.0,
        "gpu_utilization": gpu_utilization,
        "vram_available_gb": vram_available_gb,
    }


class TestScheduleAPI:
    """Tests for POST /schedule."""

    async def test_successful_scheduling(self, client: AsyncClient):
        # 1. Register node
        reg = await client.post("/nodes/register", json=_node_payload("node-1"))
        assert reg.status_code == 201

        # 2. Send heartbeat
        hb = await client.post("/heartbeat", json=_heartbeat_payload("node-1"))
        assert hb.status_code == 200

        # 3. Schedule request
        response = await client.post("/schedule", json={"model_name": "llama-3"})
        assert response.status_code == 200

        data = response.json()
        assert data["node_id"] == "node-1"
        assert data["hostname"] == "host-node-1"
        assert "ip_address" in data
        assert "region" in data

    async def test_no_registered_nodes_returns_404(self, client: AsyncClient):
        response = await client.post("/schedule", json={"model_name": "llama-3"})
        assert response.status_code == 404
        assert "no eligible nodes found" in response.json()["detail"].lower()

    async def test_node_without_heartbeat_ignored(self, client: AsyncClient):
        # Register a node, but send no heartbeat
        reg = await client.post("/nodes/register", json=_node_payload("node-1"))
        assert reg.status_code == 201

        response = await client.post("/schedule", json={"model_name": "llama-3"})
        assert response.status_code == 404

    async def test_offline_node_ignored(self, client: AsyncClient):
        reg = await client.post("/nodes/register", json=_node_payload("node-1"))
        assert reg.status_code == 201

        hb = await client.post("/heartbeat", json=_heartbeat_payload("node-1", status="offline"))
        assert hb.status_code == 200

        response = await client.post("/schedule", json={"model_name": "llama-3"})
        assert response.status_code == 404

    async def test_missing_model_ignored(self, client: AsyncClient):
        # Node does not support llama-3
        reg = await client.post(
            "/nodes/register", json=_node_payload("node-1", models=["mistral"])
        )
        assert reg.status_code == 201

        hb = await client.post("/heartbeat", json=_heartbeat_payload("node-1"))
        assert hb.status_code == 200

        response = await client.post("/schedule", json={"model_name": "llama-3"})
        assert response.status_code == 404

    async def test_best_node_selected(self, client: AsyncClient):
        # Register node 1: busy/higher score
        reg1 = await client.post("/nodes/register", json=_node_payload("node-1"))
        assert reg1.status_code == 201
        hb1 = await client.post(
            "/heartbeat",
            json=_heartbeat_payload(
                "node-1", queue_length=5, gpu_utilization=80.0, vram_available_gb=10.0
            ),
        )
        assert hb1.status_code == 200

        # Register node 2: idle/lower score
        reg2 = await client.post("/nodes/register", json=_node_payload("node-2"))
        assert reg2.status_code == 201
        hb2 = await client.post(
            "/heartbeat",
            json=_heartbeat_payload(
                "node-2", queue_length=0, gpu_utilization=10.0, vram_available_gb=50.0
            ),
        )
        assert hb2.status_code == 200

        response = await client.post("/schedule", json={"model_name": "llama-3"})
        assert response.status_code == 200
        assert response.json()["node_id"] == "node-2"

    async def test_deterministic_tie_breaking(self, client: AsyncClient):
        # Register node 1 then node 2 with identical heartbeats
        reg1 = await client.post("/nodes/register", json=_node_payload("node-1"))
        assert reg1.status_code == 201
        hb1 = await client.post("/heartbeat", json=_heartbeat_payload("node-1"))
        assert hb1.status_code == 200

        reg2 = await client.post("/nodes/register", json=_node_payload("node-2"))
        assert reg2.status_code == 201
        hb2 = await client.post("/heartbeat", json=_heartbeat_payload("node-2"))
        assert hb2.status_code == 200

        # Selection should pick node-1 (first registered)
        response = await client.post("/schedule", json={"model_name": "llama-3"})
        assert response.status_code == 200
        assert response.json()["node_id"] == "node-1"
