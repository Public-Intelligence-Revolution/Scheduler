"""Tests for the scheduling algorithm."""

from datetime import UTC, datetime

import pytest

from scheduler.models.heartbeat import Heartbeat
from scheduler.models.node import GPUInfo, Node, NodeStatus
from scheduler.registry.node_registry import NodeRegistry
from scheduler.scheduler.algorithm import Scheduler


@pytest.fixture()
def registry() -> NodeRegistry:
    return NodeRegistry()


@pytest.fixture()
def scheduler(registry: NodeRegistry) -> Scheduler:
    return Scheduler(registry)


@pytest.fixture()
def gpu() -> GPUInfo:
    return GPUInfo(name="NVIDIA A100", vram_total_gb=80.0, vram_available_gb=60.0)


@pytest.fixture()
def now() -> datetime:
    return datetime.now(tz=UTC)


def _make_node(node_id: str, gpu: GPUInfo, models: list[str]) -> Node:
    return Node(
        node_id=node_id,
        hostname=f"host-{node_id}",
        ip_address=f"10.0.0.{node_id}",
        region="us-east-1",
        gpu=gpu,
        cpu_cores=32,
        ram_total_gb=128.0,
        available_models=models,
    )


def _make_heartbeat(
    node_id: str,
    timestamp: datetime,
    status: NodeStatus = NodeStatus.ONLINE,
    queue_length: int = 0,
    cpu_utilization: float = 0.0,
    gpu_utilization: float = 0.0,
    vram_available_gb: float = 40.0,
) -> Heartbeat:
    return Heartbeat(
        node_id=node_id,
        timestamp=timestamp,
        status=status,
        queue_length=queue_length,
        cpu_utilization=cpu_utilization,
        ram_available_gb=64.0,
        gpu_utilization=gpu_utilization,
        vram_available_gb=vram_available_gb,
    )


class TestSchedulerAlgorithm:
    """Tests for deterministic compute node scheduling."""

    async def test_single_eligible_node(
        self, registry: NodeRegistry, scheduler: Scheduler, gpu: GPUInfo, now: datetime
    ):
        node = _make_node("node-1", gpu, ["llama-3"])
        await registry.register(node)
        heartbeat = _make_heartbeat("node-1", now)
        await registry.update_heartbeat(heartbeat)

        selected = await scheduler.select_node("llama-3")
        assert selected.node_id == "node-1"

    async def test_no_eligible_nodes_raises_value_error(
        self, registry: NodeRegistry, scheduler: Scheduler
    ):
        with pytest.raises(ValueError, match="No eligible nodes found"):
            await scheduler.select_node("llama-3")

    async def test_missing_model_ignored(
        self, registry: NodeRegistry, scheduler: Scheduler, gpu: GPUInfo, now: datetime
    ):
        node = _make_node("node-1", gpu, ["mistral"])
        await registry.register(node)
        heartbeat = _make_heartbeat("node-1", now)
        await registry.update_heartbeat(heartbeat)

        with pytest.raises(ValueError, match="No eligible nodes found"):
            await scheduler.select_node("llama-3")

    async def test_missing_heartbeat_ignored(
        self, registry: NodeRegistry, scheduler: Scheduler, gpu: GPUInfo
    ):
        node = _make_node("node-1", gpu, ["llama-3"])
        await registry.register(node)
        # Note: no heartbeat update

        with pytest.raises(ValueError, match="No eligible nodes found"):
            await scheduler.select_node("llama-3")

    async def test_offline_node_ignored(
        self, registry: NodeRegistry, scheduler: Scheduler, gpu: GPUInfo, now: datetime
    ):
        node = _make_node("node-1", gpu, ["llama-3"])
        await registry.register(node)
        heartbeat = _make_heartbeat("node-1", now, status=NodeStatus.OFFLINE)
        await registry.update_heartbeat(heartbeat)

        with pytest.raises(ValueError, match="No eligible nodes found"):
            await scheduler.select_node("llama-3")

    async def test_score_comparison_lowest_wins(
        self, registry: NodeRegistry, scheduler: Scheduler, gpu: GPUInfo, now: datetime
    ):
        # Node 1: High queue length, high gpu util -> higher score
        node1 = _make_node("node-1", gpu, ["llama-3"])
        await registry.register(node1)
        hb1 = _make_heartbeat(
            "node-1",
            now,
            queue_length=10,
            gpu_utilization=90.0,
            cpu_utilization=50.0,
            vram_available_gb=10.0,
        )
        await registry.update_heartbeat(hb1)

        # Node 2: Low queue length, low gpu util -> lower score
        node2 = _make_node("node-2", gpu, ["llama-3"])
        await registry.register(node2)
        hb2 = _make_heartbeat(
            "node-2",
            now,
            queue_length=1,
            gpu_utilization=10.0,
            cpu_utilization=10.0,
            vram_available_gb=50.0,
        )
        await registry.update_heartbeat(hb2)

        selected = await scheduler.select_node("llama-3")
        assert selected.node_id == "node-2"

    async def test_deterministic_tie_breaker_by_insertion_order(
        self, registry: NodeRegistry, scheduler: Scheduler, gpu: GPUInfo, now: datetime
    ):
        # Two identical nodes with exact same heartbeat values
        node1 = _make_node("node-1", gpu, ["llama-3"])
        node2 = _make_node("node-2", gpu, ["llama-3"])

        await registry.register(node1)
        await registry.register(node2)

        hb1 = _make_heartbeat("node-1", now, queue_length=0, gpu_utilization=0.0)
        hb2 = _make_heartbeat("node-2", now, queue_length=0, gpu_utilization=0.0)

        await registry.update_heartbeat(hb1)
        await registry.update_heartbeat(hb2)

        # Should select the first one registered (insertion order)
        selected = await scheduler.select_node("llama-3")
        assert selected.node_id == "node-1"

        # Reverse registration order to verify it's insertion order, not alphanumeric ID
        await registry.clear()
        await registry.register(node2)
        await registry.register(node1)
        await registry.update_heartbeat(hb2)
        await registry.update_heartbeat(hb1)

        selected_reversed = await scheduler.select_node("llama-3")
        assert selected_reversed.node_id == "node-2"

    async def test_scoring_weights_normalized(
        self, registry: NodeRegistry, scheduler: Scheduler, gpu: GPUInfo, now: datetime
    ):
        # Node 1: queue=1, gpu=50%, cpu=30%, vram_avail=40G, vram_total=80G (ratio = 0.5)
        # Score = (1 * 0.4) + (0.5 * 0.3) + (0.3 * 0.1) + ((1.0 - 0.5) * 0.2)
        #       = 0.4 + 0.15 + 0.03 + 0.10 = 0.68
        node = _make_node("node-1", gpu, ["llama-3"])
        await registry.register(node)
        hb = _make_heartbeat(
            "node-1",
            now,
            queue_length=1,
            gpu_utilization=50.0,
            cpu_utilization=30.0,
            vram_available_gb=40.0,
        )
        await registry.update_heartbeat(hb)
        selected = await scheduler.select_node("llama-3")
        assert selected.node_id == "node-1"

    async def test_scheduling_dampener_increment_and_decay(
        self, registry: NodeRegistry, scheduler: Scheduler, gpu: GPUInfo, now: datetime
    ):
        # Two identical nodes
        node1 = _make_node("node-1", gpu, ["llama-3"])
        node2 = _make_node("node-2", gpu, ["llama-3"])
        await registry.register(node1)
        await registry.register(node2)

        hb1 = _make_heartbeat("node-1", now, queue_length=0, gpu_utilization=0.0)
        hb2 = _make_heartbeat("node-2", now, queue_length=0, gpu_utilization=0.0)
        await registry.update_heartbeat(hb1)
        await registry.update_heartbeat(hb2)

        # Dampeners should start at 0.0
        assert await registry.get_dampener("node-1") == 0.0
        assert await registry.get_dampener("node-2") == 0.0

        # Selecting llama-3 should pick node-1 (due to insertion order)
        selected = await scheduler.select_node("llama-3")
        assert selected.node_id == "node-1"

        # Now node-1 dampener should be incremented to 0.1
        assert await registry.get_dampener("node-1") == 0.1
        assert await registry.get_dampener("node-2") == 0.0

        # Selecting again: node-2 has score 0.0 + 0.10 (VRAM portion) = 0.10.
        # node-1 has score 0.0 + 0.10 (VRAM portion) + 0.1 (dampener) = 0.20.
        # So node-2 should be selected now!
        selected2 = await scheduler.select_node("llama-3")
        assert selected2.node_id == "node-2"

        # Now node-2 dampener should be 0.1, and node-1 is still 0.1
        assert await registry.get_dampener("node-1") == 0.1
        assert await registry.get_dampener("node-2") == 0.1

        # An incoming heartbeat for node-1 should reset/decay its dampener to 0.0
        await registry.update_heartbeat(hb1)
        assert await registry.get_dampener("node-1") == 0.0
        assert await registry.get_dampener("node-2") == 0.1
