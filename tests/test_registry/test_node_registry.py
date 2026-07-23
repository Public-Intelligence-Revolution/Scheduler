"""Tests for the in-memory NodeRegistry."""

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest

from scheduler.models.heartbeat import Heartbeat
from scheduler.models.node import GPUInfo, Node, NodeStatus
from scheduler.registry.node_registry import NodeRegistry


@pytest.fixture()
def gpu() -> GPUInfo:
    return GPUInfo(name="NVIDIA A100", vram_total_gb=80.0, vram_available_gb=60.0)


@pytest.fixture()
def now() -> datetime:
    return datetime.now(tz=UTC)


def _make_node(node_id: str, gpu: GPUInfo) -> Node:
    """Helper to build a Node with sensible defaults."""
    return Node(
        node_id=node_id,
        hostname=f"host-{node_id}",
        ip_address=f"10.0.0.{node_id}",
        region="us-east-1",
        gpu=gpu,
        cpu_cores=32,
        ram_total_gb=128.0,
        available_models=["llama-3-70b"],
    )


class TestEmptyRegistry:
    """Tests for a freshly-created registry."""

    async def test_count_is_zero(self):
        registry = NodeRegistry()
        assert await registry.count() == 0

    async def test_list_is_empty(self):
        registry = NodeRegistry()
        assert await registry.list() == []

    async def test_get_returns_none(self):
        registry = NodeRegistry()
        assert await registry.get("nonexistent") is None

    async def test_exists_returns_false(self):
        registry = NodeRegistry()
        assert await registry.exists("nonexistent") is False


class TestRegister:
    """Tests for node registration."""

    async def test_register_node(self, gpu: GPUInfo):
        registry = NodeRegistry()
        node = _make_node("1", gpu)
        await registry.register(node)
        assert await registry.count() == 1
        assert await registry.get("1") == node

    async def test_register_duplicate_raises(self, gpu: GPUInfo):
        registry = NodeRegistry()
        node = _make_node("1", gpu)
        await registry.register(node)
        with pytest.raises(ValueError, match="Node already registered: 1"):
            await registry.register(node)


class TestExists:
    """Tests for existence checks."""

    async def test_exists_after_register(self, gpu: GPUInfo):
        registry = NodeRegistry()
        await registry.register(_make_node("1", gpu))
        assert await registry.exists("1") is True

    async def test_not_exists_after_unregister(self, gpu: GPUInfo):
        registry = NodeRegistry()
        await registry.register(_make_node("1", gpu))
        await registry.unregister("1")
        assert await registry.exists("1") is False


class TestGet:
    """Tests for node retrieval."""

    async def test_get_registered_node(self, gpu: GPUInfo):
        registry = NodeRegistry()
        node = _make_node("1", gpu)
        await registry.register(node)
        assert await registry.get("1") == node

    async def test_get_missing_node_returns_none(self):
        registry = NodeRegistry()
        assert await registry.get("missing") is None


class TestList:
    """Tests for listing nodes."""

    async def test_list_preserves_insertion_order(self, gpu: GPUInfo):
        registry = NodeRegistry()
        node_a = _make_node("a", gpu)
        node_b = _make_node("b", gpu)
        node_c = _make_node("c", gpu)
        await registry.register(node_a)
        await registry.register(node_b)
        await registry.register(node_c)
        result = await registry.list()
        assert result == [node_a, node_b, node_c]

    async def test_list_returns_copy(self, gpu: GPUInfo):
        registry = NodeRegistry()
        await registry.register(_make_node("1", gpu))
        list_a = await registry.list()
        list_b = await registry.list()
        assert list_a is not list_b


class TestUpdate:
    """Tests for node updates."""

    async def test_update_existing_node(self, gpu: GPUInfo):
        registry = NodeRegistry()
        node = _make_node("1", gpu)
        await registry.register(node)
        updated = node.model_copy(update={"available_models": ["llama-3-70b", "mistral-7b"]})
        await registry.update(updated)
        retrieved = await registry.get("1")
        assert retrieved == updated
        assert retrieved is not None
        assert retrieved.available_models == ["llama-3-70b", "mistral-7b"]

    async def test_update_missing_node_raises(self, gpu: GPUInfo):
        registry = NodeRegistry()
        node = _make_node("missing", gpu)
        with pytest.raises(ValueError, match="Node not found: missing"):
            await registry.update(node)


class TestUnregister:
    """Tests for node removal."""

    async def test_unregister_node(self, gpu: GPUInfo):
        registry = NodeRegistry()
        await registry.register(_make_node("1", gpu))
        await registry.unregister("1")
        assert await registry.count() == 0
        assert await registry.get("1") is None

    async def test_unregister_missing_node_raises(self):
        registry = NodeRegistry()
        with pytest.raises(ValueError, match="Node not found: missing"):
            await registry.unregister("missing")


class TestClear:
    """Tests for clearing the registry."""

    async def test_clear_removes_all(self, gpu: GPUInfo):
        registry = NodeRegistry()
        await registry.register(_make_node("1", gpu))
        await registry.register(_make_node("2", gpu))
        await registry.clear()
        assert await registry.count() == 0
        assert await registry.list() == []

    async def test_clear_empty_registry(self):
        registry = NodeRegistry()
        await registry.clear()
        assert await registry.count() == 0


class TestCount:
    """Tests for counting nodes."""

    async def test_count_increments(self, gpu: GPUInfo):
        registry = NodeRegistry()
        assert await registry.count() == 0
        await registry.register(_make_node("1", gpu))
        assert await registry.count() == 1
        await registry.register(_make_node("2", gpu))
        assert await registry.count() == 2

    async def test_count_decrements_on_unregister(self, gpu: GPUInfo):
        registry = NodeRegistry()
        await registry.register(_make_node("1", gpu))
        await registry.register(_make_node("2", gpu))
        await registry.unregister("1")
        assert await registry.count() == 1


class TestThreadSafety:
    """Basic thread-safety sanity check using asyncio."""

    async def test_concurrent_register(self, gpu: GPUInfo):
        registry = NodeRegistry()
        errors: list[Exception] = []

        async def register_node(node_id: str) -> None:
            try:
                await registry.register(_make_node(node_id, gpu))
            except Exception as e:
                errors.append(e)

        tasks = [register_node(str(i)) for i in range(100)]
        await asyncio.gather(*tasks)

        assert len(errors) == 0
        assert await registry.count() == 100

    async def test_concurrent_register_and_read(self, gpu: GPUInfo):
        registry = NodeRegistry()
        # Pre-register some nodes
        for i in range(50):
            await registry.register(_make_node(f"pre-{i}", gpu))

        read_results: list[int] = []
        errors: list[Exception] = []

        async def register_node(node_id: str) -> None:
            try:
                await registry.register(_make_node(node_id, gpu))
            except Exception as e:
                errors.append(e)

        async def read_nodes() -> None:
            try:
                read_results.append(len(await registry.list()))
            except Exception as e:
                errors.append(e)

        tasks: list[Any] = []
        for i in range(50):
            tasks.append(register_node(f"new-{i}"))
            tasks.append(read_nodes())

        await asyncio.gather(*tasks)

        assert len(errors) == 0
        assert await registry.count() == 100


class TestHeartbeatUpdates:
    """Tests for NodeRegistry heartbeat functionality."""

    async def test_update_heartbeat_success(self, gpu: GPUInfo, now: datetime):
        registry = NodeRegistry()
        node = _make_node("1", gpu)
        await registry.register(node)

        heartbeat = Heartbeat(
            node_id="1",
            timestamp=now,
            status=NodeStatus.BUSY,
            queue_length=5,
            cpu_utilization=45.0,
            ram_available_gb=32.0,
            gpu_utilization=90.0,
            vram_available_gb=24.0,
        )

        await registry.update_heartbeat(heartbeat)
        retrieved = await registry.get_heartbeat("1")
        assert retrieved == heartbeat

    async def test_update_heartbeat_unknown_node_raises(self, now: datetime):
        registry = NodeRegistry()
        heartbeat = Heartbeat(
            node_id="unknown",
            timestamp=now,
            status=NodeStatus.ONLINE,
            queue_length=0,
            cpu_utilization=10.0,
            ram_available_gb=64.0,
            gpu_utilization=10.0,
            vram_available_gb=40.0,
        )

        with pytest.raises(ValueError, match="Node not found: unknown"):
            await registry.update_heartbeat(heartbeat)

    async def test_multiple_heartbeats_updates_values_and_timestamp(
        self, gpu: GPUInfo, now: datetime
    ):
        registry = NodeRegistry()
        node = _make_node("1", gpu)
        await registry.register(node)

        from datetime import timedelta

        hb1 = Heartbeat(
            node_id="1",
            timestamp=now,
            status=NodeStatus.ONLINE,
            queue_length=2,
            cpu_utilization=20.0,
            ram_available_gb=60.0,
            gpu_utilization=30.0,
            vram_available_gb=50.0,
        )
        await registry.update_heartbeat(hb1)

        later = now + timedelta(minutes=1)
        hb2 = Heartbeat(
            node_id="1",
            timestamp=later,
            status=NodeStatus.BUSY,
            queue_length=10,
            cpu_utilization=95.0,
            ram_available_gb=10.0,
            gpu_utilization=99.0,
            vram_available_gb=5.0,
        )
        await registry.update_heartbeat(hb2)

        retrieved = await registry.get_heartbeat("1")
        assert retrieved is not None
        assert retrieved.timestamp == later
        assert retrieved.status == NodeStatus.BUSY
        assert retrieved.queue_length == 10
        assert retrieved.cpu_utilization == 95.0
        assert retrieved.ram_available_gb == 10.0
        assert retrieved.gpu_utilization == 99.0
        assert retrieved.vram_available_gb == 5.0

    async def test_unregister_cleans_heartbeat(self, gpu: GPUInfo, now: datetime):
        registry = NodeRegistry()
        node = _make_node("1", gpu)
        await registry.register(node)

        heartbeat = Heartbeat(
            node_id="1",
            timestamp=now,
            status=NodeStatus.ONLINE,
            queue_length=0,
            cpu_utilization=0.0,
            ram_available_gb=64.0,
            gpu_utilization=0.0,
            vram_available_gb=40.0,
        )
        await registry.update_heartbeat(heartbeat)
        assert await registry.get_heartbeat("1") is not None

        await registry.unregister("1")
        assert await registry.get_heartbeat("1") is None

    async def test_unregister_cleans_telemetry(self, gpu: GPUInfo):
        registry = NodeRegistry()
        node = _make_node("1", gpu)
        await registry.register(node)
        registry._telemetry["1"] = {"cpu_utilization": 50.0}
        assert "1" in registry._telemetry

        await registry.unregister("1")
        assert "1" not in registry._telemetry

    async def test_unregister_node_cleans_telemetry(self, gpu: GPUInfo):
        registry = NodeRegistry()
        node = _make_node("2", gpu)
        await registry.register(node)
        registry._telemetry["2"] = {"cpu_utilization": 50.0}
        assert "2" in registry._telemetry

        await registry.unregister_node("2")
        assert "2" not in registry._telemetry
