"""Unit and integration tests for the multi-stage scheduling engine."""

import pytest

from scheduler.core.engine import SchedulingEngine
from scheduler.core.matchmaker import CapabilityMatchmaker
from scheduler.models.node import GPUInfo, Node
from scheduler.registry.node_registry import NodeRegistry


@pytest.fixture
def test_nodes() -> list[Node]:
    """Construct a set of mock compute nodes with varying specs and models."""
    node1 = Node(
        node_id="node-1",
        hostname="host-1",
        ip_address="127.0.0.1",
        region="us-east",
        gpu=GPUInfo(name="RTX 4090", vram_total_gb=24.0, vram_available_gb=20.0),
        cpu_cores=8,
        ram_total_gb=32.0,
        available_models=["llama3", "mistral"],
    )
    node2 = Node(
        node_id="node-2",
        hostname="host-2",
        ip_address="127.0.0.2",
        region="us-west",
        gpu=GPUInfo(name="RTX 3080", vram_total_gb=10.0, vram_available_gb=5.0),
        cpu_cores=4,
        ram_total_gb=16.0,
        available_models=["llama3"],
    )
    node3 = Node(
        node_id="node-3",
        hostname="host-3",
        ip_address="127.0.0.3",
        region="eu-west",
        gpu=GPUInfo(name="H100", vram_total_gb=80.0, vram_available_gb=80.0),
        cpu_cores=32,
        ram_total_gb=128.0,
        available_models=["llama3", "mixtral"],
    )
    return [node1, node2, node3]


@pytest.mark.asyncio
async def test_filtering_hard_requirements(test_nodes: list[Node]) -> None:
    """Verify that nodes failing hard model or VRAM requirements are filtered out."""
    registry = NodeRegistry()
    for node in test_nodes:
        await registry.local_register(node)

    strategy = CapabilityMatchmaker(registry)

    # 1. Test model filtering (mixtral is only supported by node-3)
    reqs_model = {"model_name": "mixtral"}
    filtered_model = strategy.filter_nodes(reqs_model, test_nodes)
    assert len(filtered_model) == 1
    assert filtered_model[0].node_id == "node-3"

    # 2. Test VRAM filtering (min 16GB VRAM satisfies node-1 and node-3)
    reqs_vram = {"min_vram_gb": 16.0}
    filtered_vram = strategy.filter_nodes(reqs_vram, test_nodes)
    assert len(filtered_vram) == 2
    assert {n.node_id for n in filtered_vram} == {"node-1", "node-3"}


@pytest.mark.asyncio
async def test_load_and_reliability_scoring(test_nodes: list[Node]) -> None:
    """Verify that nodes with identical models are ranked based on active load and reliability."""
    registry = NodeRegistry()
    for node in test_nodes:
        await registry.local_register(node)

    # Set custom telemetry to differentiate rank
    registry._telemetry["node-1"] = {
        "queue_depth": 2,
        "cpu_utilization": 50.0,
        "reliability_score": 0.9,
    }
    registry._telemetry["node-2"] = {
        "queue_depth": 0,
        "cpu_utilization": 10.0,
        "reliability_score": 0.95,
    }
    registry._telemetry["node-3"] = {
        "queue_depth": 1,
        "cpu_utilization": 80.0,
        "reliability_score": 0.98,
    }

    strategy = CapabilityMatchmaker(registry)

    eligible = strategy.filter_nodes({"model_name": "llama3"}, test_nodes)
    assert len(eligible) == 3

    ranked = strategy.score_nodes({}, eligible)

    # Expected fitness score calculations:
    # node-2: (0.95 * 100) - (0 * 15) - (10 * 0.5) = 95 - 0 - 5 = 90.0
    # node-3: (0.98 * 100) - (1 * 15) - (80 * 0.5) = 98 - 15 - 40 = 43.0
    # node-1: (0.90 * 100) - (2 * 15) - (50 * 0.5) = 90 - 30 - 25 = 35.0
    assert ranked[0][0].node_id == "node-2"
    assert ranked[1][0].node_id == "node-3"
    assert ranked[2][0].node_id == "node-1"


@pytest.mark.asyncio
async def test_scheduling_engine_routing(test_nodes: list[Node]) -> None:
    """Verify that incoming tasks are scheduled to the highest-scoring eligible node."""
    registry = NodeRegistry()
    # Only register node-1 and node-2
    await registry.local_register(test_nodes[0])
    await registry.local_register(test_nodes[1])

    registry._telemetry["node-1"] = {
        "queue_depth": 0,
        "cpu_utilization": 10.0,
        "reliability_score": 0.9,
    }
    registry._telemetry["node-2"] = {
        "queue_depth": 0,
        "cpu_utilization": 50.0,
        "reliability_score": 0.9,
    }

    strategy = CapabilityMatchmaker(registry)
    engine = SchedulingEngine(registry, strategy)

    task = {
        "task_id": "task-test-uuid",
        "requirements": {"model_name": "llama3"},
    }

    # Should select node-1 due to lower CPU utilization
    tx_hash = await engine.schedule_task(task)
    assert isinstance(tx_hash, str)
    assert len(tx_hash) == 64  # Valid SHA-256 hex digest length

    # Verify queue depth is dynamically updated in NodeRegistry
    assert registry._telemetry["node-1"]["queue_depth"] == 1
