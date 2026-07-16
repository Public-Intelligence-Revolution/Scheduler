"""Unit and integration tests for the Scheduler transport layer."""

import asyncio
import json

import pytest
import zenoh

from scheduler.core.transport import BackpressuredReceiver, SharedMemoryIPC


def test_shared_memory_ipc_lifecycle() -> None:
    """Verify that SharedMemoryIPC can create, read, and clean up a shared memory block."""
    payload = b"hello scheduler zero copy payload"
    shm_name = SharedMemoryIPC.write_data(payload)

    try:
        assert shm_name.startswith("pi_shm_")

        # Read back data
        read_payload = SharedMemoryIPC.read_data(shm_name)
        assert read_payload == payload
    finally:
        # Clean up
        SharedMemoryIPC.cleanup(shm_name)

        # Attempting to read after cleanup should fail
        with pytest.raises(FileNotFoundError):
            SharedMemoryIPC.read_data(shm_name)


@pytest.mark.asyncio
async def test_backpressured_receiver_sends_acks() -> None:
    """Verify that BackpressuredReceiver publishes sequential capacity ACKs over Zenoh."""
    # Open local Zenoh session
    config = zenoh.Config()
    # Disable multicast scouting to prevent local network interference in test run
    config.insert_json5("scouting/multicast/enabled", "false")

    with zenoh.open(config) as session:
        session_id = "test-session-receiver-ack"
        receiver = BackpressuredReceiver(session_id, session)

        received_acks = []

        def ack_callback(sample: zenoh.Sample) -> None:
            try:
                payload_str = sample.payload.to_string()
            except AttributeError:
                try:
                    payload_str = sample.payload.decode("utf-8")  # type: ignore[attr-defined]
                except (AttributeError, UnicodeDecodeError):
                    payload_str = str(sample.payload)
            try:
                data = json.loads(payload_str)
                received_acks.append(data)
            except Exception:
                pass

        # Subscribe to ACK topic
        ack_topic = f"public-intelligence/net/transport/ack/{session_id}"
        subscriber = session.declare_subscriber(ack_topic, ack_callback)

        # Send ACK
        receiver.send_ack()

        # Wait a moment for delivery
        await asyncio.sleep(0.5)

        assert len(received_acks) == 1
        assert received_acks[0]["seq"] == 1

        # Send another ACK
        receiver.send_ack()

        # Wait a moment for delivery
        await asyncio.sleep(0.5)

        assert len(received_acks) == 2
        assert received_acks[1]["seq"] == 2

        subscriber.undeclare()  # type: ignore[no-untyped-call]
