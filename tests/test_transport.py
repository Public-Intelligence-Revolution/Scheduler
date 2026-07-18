"""Unit and integration tests for the Scheduler transport layer."""

import asyncio
import json
import logging

import pytest
import zenoh

from scheduler.core.transport import BackpressuredReceiver, SharedMemoryIPC

logger = logging.getLogger(__name__)


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


@pytest.mark.asyncio
async def test_backpressured_receiver_stream_consumption() -> None:
    """Verify that BackpressuredReceiver consumes stream chunks (local & remote) and sends ACKs."""
    config = zenoh.Config()
    config.insert_json5("scouting/multicast/enabled", "false")

    with zenoh.open(config) as session:
        session_id = "test-session-stream-receiver"
        receiver = BackpressuredReceiver(session_id, session)

        processed_chunks = []

        def on_chunk(chunk: bytes) -> None:
            processed_chunks.append(chunk)

        # Start subscribing
        receiver.start(on_chunk)

        # Monitor ACKs published by receiver
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

        ack_topic = f"public-intelligence/net/transport/ack/{session_id}"
        ack_sub = session.declare_subscriber(ack_topic, ack_callback)

        # Wait a moment for setup
        await asyncio.sleep(0.1)

        # 1. Publish remote raw chunk over Zenoh
        stream_topic = f"public-intelligence/net/transport/stream/{session_id}"
        session.put(stream_topic, b"remote-chunk-data")

        # Wait for delivery
        await asyncio.sleep(0.3)

        assert len(processed_chunks) == 1
        assert processed_chunks[0] == b"remote-chunk-data"
        assert len(received_acks) == 1
        assert received_acks[0]["seq"] == 1

        # 2. Publish local shared memory token chunk over Zenoh
        shm_data = b"local-zero-copy-shm-data"
        shm_name = SharedMemoryIPC.write_data(shm_data)
        token = f"shm://{shm_name}"

        session.put(stream_topic, token)

        # Wait for delivery
        await asyncio.sleep(0.3)

        # The receiver should have read the data from shared memory, cleaned it up, and appended it
        assert len(processed_chunks) == 2
        assert processed_chunks[1] == shm_data

        # Verify shared memory block was cleaned up/unlinked
        with pytest.raises(FileNotFoundError):
            SharedMemoryIPC.read_data(shm_name)

        assert len(received_acks) == 2
        assert received_acks[1]["seq"] == 2

        # Clean up
        receiver.stop()
        ack_sub.undeclare()  # type: ignore[no-untyped-call]
