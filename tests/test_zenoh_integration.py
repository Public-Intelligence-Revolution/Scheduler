"""Integration tests for the Zenoh router heartbeat transport."""

import asyncio
import json
from datetime import UTC, datetime

import pytest
import zenoh

from scheduler.core.zenoh_router import ZenohRouter
from scheduler.models.node import GPUInfo, Node
from scheduler.registry.node_registry import NodeRegistry


@pytest.fixture()
def node_id() -> str:
    return "test-node-zenoh"


@pytest.fixture()
def test_node(node_id: str) -> Node:
    return Node(
        node_id=node_id,
        hostname="test-host",
        ip_address="127.0.0.1",
        region="local",
        gpu=GPUInfo(name="unknown", vram_total_gb=16.0, vram_available_gb=16.0),
        cpu_cores=4,
        ram_total_gb=16.0,
        available_models=["llama2"],
    )


@pytest.mark.asyncio
async def test_zenoh_heartbeat_routing(test_node: Node, node_id: str) -> None:
    # 1. Create registry and register node
    registry = NodeRegistry()
    await registry.register(test_node)

    # Configure Router session to listen on TCP loopback and disable multicast scouting
    router_config = zenoh.Config()
    router_config.insert_json5("listen/endpoints", '["tcp/127.0.0.1:7449"]')
    router_config.insert_json5("scouting/multicast/enabled", "false")

    # 2. Start ZenohRouter with the custom configuration
    router = ZenohRouter(registry, config=router_config)
    router.start()

    # Configure Publisher session to connect directly to the Router TCP endpoint
    pub_config = zenoh.Config()
    pub_config.insert_json5("connect/endpoints", '["tcp/127.0.0.1:7449"]')
    pub_config.insert_json5("scouting/multicast/enabled", "false")

    try:
        # 3. Create a local Zenoh session and publisher to publish mock heartbeat
        with zenoh.open(pub_config) as session:
            pub_key = f"public-intelligence/net/{node_id}/heartbeat"
            publisher = session.declare_publisher(pub_key)

            # Wait a short moment to ensure the TCP handshake is fully complete
            await asyncio.sleep(0.2)

            heartbeat_data = {
                "node_id": node_id,
                "timestamp": datetime.now(UTC).isoformat(),
                "status": "online",
                "queue_length": 3,
                "cpu_utilization": 25.5,
                "ram_available_gb": 12.0,
                "gpu_utilization": 50.0,
                "vram_available_gb": 8.0,
            }

            publisher.put(json.dumps(heartbeat_data))
            publisher.undeclare()  # type: ignore[no-untyped-call]

        # 4. Wait for the background Zenoh threads to deliver and process the heartbeat
        # (needs a small sleep as callback delivery is asynchronous across threads)
        for _ in range(20):
            hb = await registry.get_heartbeat(node_id)
            if hb is not None:
                break
            await asyncio.sleep(0.05)

        # 5. Verify the registry updated the heartbeat successfully
        hb = await registry.get_heartbeat(node_id)
        assert hb is not None, "Heartbeat was not processed by ZenohRouter"
        assert hb.node_id == node_id
        assert hb.queue_length == 3
        assert hb.cpu_utilization == 25.5
        assert hb.ram_available_gb == 12.0
        assert hb.gpu_utilization == 50.0
        assert hb.vram_available_gb == 8.0

        # Verify the dampener invariant was decayed to 0.0 on heartbeat update
        dampener = await registry.get_dampener(node_id)
        assert dampener == 0.0

    finally:
        # 6. Stop ZenohRouter cleanly
        router.stop()


@pytest.mark.asyncio
async def test_zenoh_liveliness_deathrattle(test_node: Node, node_id: str) -> None:
    # 1. Create registry and register node
    registry = NodeRegistry()
    await registry.register(test_node)
    assert await registry.exists(node_id) is True

    # Configure Router session to listen on TCP loopback and disable multicast scouting
    router_config = zenoh.Config()
    router_config.insert_json5("listen/endpoints", '["tcp/127.0.0.1:7450"]')
    router_config.insert_json5("scouting/multicast/enabled", "false")

    # 2. Start ZenohRouter with the custom configuration
    router = ZenohRouter(registry, config=router_config)
    router.start()

    # Configure Publisher session to connect directly to the Router TCP endpoint
    pub_config = zenoh.Config()
    pub_config.insert_json5("connect/endpoints", '["tcp/127.0.0.1:7450"]')
    pub_config.insert_json5("scouting/multicast/enabled", "false")

    try:
        # 3. Create a local Zenoh session and declare a liveliness token
        session = zenoh.open(pub_config)
        token_path = f"public-intelligence/net/liveliness/{node_id}"
        token = session.liveliness().declare_token(token_path)

        # Wait a short moment to ensure the TCP handshake is fully complete
        await asyncio.sleep(0.2)

        # 4. Now simulate sudden node session drop by closing the session abruptly
        token.undeclare()  # type: ignore[no-untyped-call]
        session.close()  # type: ignore[no-untyped-call]

        # 5. Wait for the background Zenoh threads to process the deathrattle (DELETE event)
        for _ in range(30):
            exists = await registry.exists(node_id)
            if not exists:
                break
            await asyncio.sleep(0.05)

        # 6. Verify the registry unregistered the node successfully
        assert not await registry.exists(node_id), "Node not unregistered on deathrattle"

    finally:
        # 7. Stop ZenohRouter cleanly
        router.stop()


@pytest.mark.asyncio
async def test_zenoh_telemetry_mapping(test_node: Node, node_id: str) -> None:
    # 1. Create registry and register node
    registry = NodeRegistry()
    await registry.register(test_node)

    # Configure Router session to listen on TCP loopback
    router_config = zenoh.Config()
    router_config.insert_json5("listen/endpoints", '["tcp/127.0.0.1:7451"]')
    router_config.insert_json5("scouting/multicast/enabled", "false")

    # 2. Start ZenohRouter
    router = ZenohRouter(registry, config=router_config)
    router.start()

    # Configure Publisher session to connect directly to the Router TCP endpoint
    pub_config = zenoh.Config()
    pub_config.insert_json5("connect/endpoints", '["tcp/127.0.0.1:7451"]')
    pub_config.insert_json5("scouting/multicast/enabled", "false")

    try:
        # 3. Create a local Zenoh session and publisher
        with zenoh.open(pub_config) as session:
            pub_key = f"public-intelligence/net/nodes/{node_id}/telemetry"
            publisher = session.declare_publisher(pub_key)

            await asyncio.sleep(0.2)

            telemetry_data = {
                "node_id": node_id,
                "timestamp": datetime.now(UTC).isoformat(),
                "cpu_utilization": 42.5,
                "ram_usage_bytes": 10737418240,
                "gpu_utilization": 20.0,
                "vram_usage_bytes": 4294967296,
            }

            publisher.put(json.dumps(telemetry_data))
            publisher.undeclare()  # type: ignore[no-untyped-call]

        # 4. Wait for background delivery
        for _ in range(30):
            if hasattr(registry, "_telemetry") and node_id in registry._telemetry:
                break
            await asyncio.sleep(0.05)

        # 5. Verify the telemetry state mapping
        assert hasattr(registry, "_telemetry"), "Registry does not have _telemetry state"
        mapped_data = registry._telemetry[node_id]
        assert mapped_data["node_id"] == node_id
        assert mapped_data["cpu_utilization"] == 42.5
        assert mapped_data["ram_usage_bytes"] == 10737418240
        assert mapped_data["gpu_utilization"] == 20.0
        assert mapped_data["vram_usage_bytes"] == 4294967296

    finally:
        router.stop()
