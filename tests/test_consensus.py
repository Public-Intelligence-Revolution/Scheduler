"""Integration tests for the Raft-based consensus state replication."""

import asyncio

import pytest
import zenoh

from scheduler.core.consensus import RaftConsensusEngine
from scheduler.models.node import GPUInfo, Node
from scheduler.registry.node_registry import NodeRegistry


@pytest.fixture()
def test_node() -> Node:
    """Fixture providing a mock Node."""
    return Node(
        node_id="test-node-consensus",
        hostname="test-host",
        ip_address="127.0.0.1",
        region="local",
        gpu=GPUInfo(name="unknown", vram_total_gb=16.0, vram_available_gb=16.0),
        cpu_cores=4,
        ram_total_gb=16.0,
        available_models=["llama2"],
    )


@pytest.fixture()
def test_node_partition() -> Node:
    """Fixture providing a second mock Node for partition testing."""
    return Node(
        node_id="partition-node-consensus",
        hostname="partition-host",
        ip_address="127.0.0.1",
        region="local",
        gpu=GPUInfo(name="unknown", vram_total_gb=16.0, vram_available_gb=16.0),
        cpu_cores=4,
        ram_total_gb=16.0,
        available_models=["llama2"],
    )


@pytest.mark.asyncio
async def test_consensus_leader_election_and_replication(
    test_node: Node, test_node_partition: Node
) -> None:
    """Test leader election, log replication, and minority partition blocking."""
    # 1. Initialize registries and consensus engines
    r1 = NodeRegistry()
    r2 = NodeRegistry()
    r3 = NodeRegistry()

    # Configure Zenoh to connect locally without wide-area mesh scouting to be fast
    config = zenoh.Config()

    c1 = RaftConsensusEngine("sched-1", r1, config)
    c2 = RaftConsensusEngine("sched-2", r2, config)
    c3 = RaftConsensusEngine("sched-3", r3, config)

    # 2. Start the consensus cluster
    await c1.start()
    await c2.start()
    await c3.start()

    try:
        # Wait up to 5 seconds for leader election to complete
        leader_engine = None
        for _ in range(50):
            if c1.state == "LEADER":
                leader_engine = c1
                break
            if c2.state == "LEADER":
                leader_engine = c2
                break
            if c3.state == "LEADER":
                leader_engine = c3
                break
            await asyncio.sleep(0.1)

        assert leader_engine is not None, "Consensus leader was not elected"

        # 3. Propose node registration on the leader
        await leader_engine.propose("register", test_node.model_dump())

        # Wait a short moment for logs to replicate and commit
        await asyncio.sleep(0.5)

        # Assert node is registered in all three registries (atomic replication)
        assert await r1.exists(test_node.node_id) is True
        assert await r2.exists(test_node.node_id) is True
        assert await r3.exists(test_node.node_id) is True

        # 4. Simulate a minority network partition: stop c3
        await c3.stop()

        # Wait for a new leader to be elected between c1 and c2 (failover election)
        new_leader = None
        for _ in range(30):
            if c1.state == "LEADER":
                new_leader = c1
                break
            if c2.state == "LEADER":
                new_leader = c2
                break
            await asyncio.sleep(0.1)

        assert new_leader is not None, "Failover leader was not elected"

        # Propose another registration (should still succeed since 2/3 is a majority quorum)
        await new_leader.propose("register", test_node_partition.model_dump())

        await asyncio.sleep(0.5)
        assert await r1.exists(test_node_partition.node_id) is True
        assert await r2.exists(test_node_partition.node_id) is True

        # 5. Simulate loss of quorum: stop c2
        await c2.stop()

        # Propose registration on c1 (should fail/timeout since only 1/3 is active)
        failed_node = Node(
            node_id="failed-node-consensus",
            hostname="failed-host",
            ip_address="127.0.0.1",
            region="local",
            gpu=GPUInfo(name="unknown", vram_total_gb=16.0, vram_available_gb=16.0),
            cpu_cores=4,
            ram_total_gb=16.0,
            available_models=["llama2"],
        )

        with pytest.raises((TimeoutError, RuntimeError)):
            await c1.propose("register", failed_node.model_dump())

    finally:
        # Cleanup
        await c1.stop()
        await c2.stop()
        await c3.stop()
