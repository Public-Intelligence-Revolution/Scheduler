"""Tests for node registration and discovery API endpoints."""

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


class TestRegisterNode:
    """Tests for POST /nodes/register."""

    async def test_register_success(self, client: AsyncClient):
        response = await client.post("/nodes/register", json=_node_payload())
        assert response.status_code == 201
        data = response.json()
        assert data["node_id"] == "node-001"
        assert data["hostname"] == "host-node-001"

    async def test_register_returns_full_node(self, client: AsyncClient):
        payload = _node_payload()
        response = await client.post("/nodes/register", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["gpu"]["name"] == "NVIDIA A100"
        assert data["cpu_cores"] == 32
        assert data["available_models"] == ["llama-3-70b"]

    async def test_register_duplicate_returns_409(self, client: AsyncClient):
        payload = _node_payload("dup-node")
        response1 = await client.post("/nodes/register", json=payload)
        assert response1.status_code == 201
        response2 = await client.post("/nodes/register", json=payload)
        assert response2.status_code == 409
        assert "already registered" in response2.json()["detail"]

    async def test_register_invalid_body_returns_422(self, client: AsyncClient):
        response = await client.post("/nodes/register", json={"bad": "data"})
        assert response.status_code == 422


class TestListNodes:
    """Tests for GET /nodes."""

    async def test_list_empty(self, client: AsyncClient):
        response = await client.get("/nodes")
        assert response.status_code == 200
        assert response.json() == []

    async def test_list_after_register(self, client: AsyncClient):
        await client.post("/nodes/register", json=_node_payload("node-a"))
        await client.post("/nodes/register", json=_node_payload("node-b"))
        response = await client.get("/nodes")
        assert response.status_code == 200
        nodes = response.json()
        assert len(nodes) == 2
        assert nodes[0]["node_id"] == "node-a"
        assert nodes[1]["node_id"] == "node-b"


class TestGetNode:
    """Tests for GET /nodes/{node_id}."""

    async def test_get_existing_node(self, client: AsyncClient):
        await client.post("/nodes/register", json=_node_payload("node-x"))
        response = await client.get("/nodes/node-x")
        assert response.status_code == 200
        assert response.json()["node_id"] == "node-x"

    async def test_get_missing_node_returns_404(self, client: AsyncClient):
        response = await client.get("/nodes/nonexistent")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
