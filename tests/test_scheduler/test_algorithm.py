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

    def test_single_eligible_node(
        self, registry: NodeRegistry, scheduler: Scheduler, gpu: GPUInfo, now: datetime
    ):
        node = _make_node("node-1", gpu, ["llama-3"])
        registry.register(node)
        heartbeat = _make_heartbeat("node-1", now)
        registry.update_heartbeat(heartbeat)

        selected = scheduler.select_node("llama-3")
        assert selected.node_id == "node-1"

    def test_no_eligible_nodes_raises_value_error(
        self, registry: NodeRegistry, scheduler: Scheduler
    ):
        with pytest.raises(ValueError, match="No eligible nodes found"):
            scheduler.select_node("llama-3")

    def test_missing_model_ignored(
        self, registry: NodeRegistry, scheduler: Scheduler, gpu: GPUInfo, now: datetime
    ):
        node = _make_node("node-1", gpu, ["mistral"])
        registry.register(node)
        heartbeat = _make_heartbeat("node-1", now)
        registry.update_heartbeat(heartbeat)

        with pytest.raises(ValueError, match="No eligible nodes found"):
            scheduler.select_node("llama-3")

    def test_missing_heartbeat_ignored(
        self, registry: NodeRegistry, scheduler: Scheduler, gpu: GPUInfo
    ):
        node = _make_node("node-1", gpu, ["llama-3"])
        registry.register(node)
        # Note: no heartbeat update

        with pytest.raises(ValueError, match="No eligible nodes found"):
            scheduler.select_node("llama-3")

    def test_offline_node_ignored(
        self, registry: NodeRegistry, scheduler: Scheduler, gpu: GPUInfo, now: datetime
    ):
        node = _make_node("node-1", gpu, ["llama-3"])
        registry.register(node)
        heartbeat = _make_heartbeat("node-1", now, status=NodeStatus.OFFLINE)
        registry.update_heartbeat(heartbeat)

        with pytest.raises(ValueError, match="No eligible nodes found"):
            scheduler.select_node("llama-3")

    def test_score_comparison_lowest_wins(
        self, registry: NodeRegistry, scheduler: Scheduler, gpu: GPUInfo, now: datetime
    ):
        # Node 1: High queue length, high gpu util -> higher score
        node1 = _make_node("node-1", gpu, ["llama-3"])
        registry.register(node1)
        hb1 = _make_heartbeat(
            "node-1",
            now,
            queue_length=10,
            gpu_utilization=90.0,
            cpu_utilization=50.0,
            vram_available_gb=10.0,
        )
        registry.update_heartbeat(hb1)

        # Node 2: Low queue length, low gpu util -> lower score
        node2 = _make_node("node-2", gpu, ["llama-3"])
        registry.register(node2)
        hb2 = _make_heartbeat(
            "node-2",
            now,
            queue_length=1,
            gpu_utilization=10.0,
            cpu_utilization=10.0,
            vram_available_gb=50.0,
        )
        registry.update_heartbeat(hb2)

        selected = scheduler.select_node("llama-3")
        assert selected.node_id == "node-2"

    def test_deterministic_tie_breaker_by_insertion_order(
        self, registry: NodeRegistry, scheduler: Scheduler, gpu: GPUInfo, now: datetime
    ):
        # Two identical nodes with exact same heartbeat values
        node1 = _make_node("node-1", gpu, ["llama-3"])
        node2 = _make_node("node-2", gpu, ["llama-3"])

        registry.register(node1)
        registry.register(node2)

        hb1 = _make_heartbeat("node-1", now, queue_length=0, gpu_utilization=0.0)
        hb2 = _make_heartbeat("node-2", now, queue_length=0, gpu_utilization=0.0)

        registry.update_heartbeat(hb1)
        registry.update_heartbeat(hb2)

        # Should select the first one registered (insertion order)
        selected = scheduler.select_node("llama-3")
        assert selected.node_id == "node-1"

        # Reverse registration order to verify it's insertion order, not alphanumeric ID
        registry.clear()
        registry.register(node2)
        registry.register(node1)
        registry.update_heartbeat(hb2)
        registry.update_heartbeat(hb1)

        selected_reversed = scheduler.select_node("llama-3")
        assert selected_reversed.node_id == "node-2"
