"""Transport layer implementing SharedMemory IPC and Backpressured WAN routing on Scheduler."""

import asyncio
import json
import logging
from collections.abc import Callable
from multiprocessing import shared_memory
from typing import Any

import zenoh

logger = logging.getLogger(__name__)


class SharedMemoryIPC:
    """Zero-copy Shared Memory bridge for local co-located process communication."""

    @staticmethod
    def write_data(data: bytes) -> str:
        """Create a shared memory block and write bytes data to it.

        Args:
            data: Binary payload to write.

        Returns:
            The unique string name of the shared memory block.
        """
        import uuid

        name = f"pi_shm_{uuid.uuid4().hex[:12]}"
        shm = shared_memory.SharedMemory(name=name, create=True, size=len(data) + 4)
        try:
            shm.buf[:4] = len(data).to_bytes(4, "big")  # type: ignore[index]
            shm.buf[4 : 4 + len(data)] = data  # type: ignore[index]
        finally:
            shm.close()
        return name

    @staticmethod
    def read_data(name: str) -> bytes:
        """Read data from an existing shared memory block.

        Args:
            name: String name of the shared memory block.

        Returns:
            The read binary payload.
        """
        shm = shared_memory.SharedMemory(name=name)
        try:
            data_len = int.from_bytes(shm.buf[:4], "big")  # type: ignore[index]
            data = bytes(shm.buf[4 : 4 + data_len])  # type: ignore[index]
        finally:
            shm.close()
        return data

    @staticmethod
    def cleanup(name: str) -> None:
        """Clean up and unlink a shared memory block.

        Args:
            name: String name of the shared memory block.
        """
        try:
            shm = shared_memory.SharedMemory(name=name)
            shm.close()
            shm.unlink()
        except Exception as e:
            logger.debug("SharedMemory cleanup failed for %s: %s", name, e)


class BackpressuredReceiver:
    """Receiver-side flow control helper to send acknowledgments back to the sender."""

    def __init__(self, session_id: str, zenoh_session: zenoh.Session) -> None:
        """Initialize the BackpressuredReceiver.

        Args:
            session_id: Unique streaming session ID.
            zenoh_session: Active Zenoh session.
        """
        self.session_id = session_id
        self.zenoh_session = zenoh_session
        self.ack_topic = f"public-intelligence/net/transport/ack/{self.session_id}"
        self.processed_count = 0
        self.subscriber: zenoh.Subscriber[Any] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def send_ack(self) -> None:
        """Publish a processing capacity signal (ACK) back to the stream router."""
        self.processed_count += 1
        payload = json.dumps({"seq": self.processed_count})
        self.zenoh_session.put(self.ack_topic, payload)

    def start(self, on_chunk: Callable[[bytes], Any]) -> None:
        """Subscribe to the stream topic and process incoming chunks."""
        self.stream_topic = f"public-intelligence/net/transport/stream/{self.session_id}"
        self._loop = asyncio.get_running_loop()

        def _on_sample(sample: zenoh.Sample) -> None:
            try:
                payload_str = sample.payload.to_string()
            except AttributeError:
                try:
                    payload_str = sample.payload.decode("utf-8")  # type: ignore[attr-defined]
                except (AttributeError, UnicodeDecodeError):
                    payload_str = str(sample.payload)

            data: bytes
            if payload_str.startswith("shm://"):
                shm_name = payload_str[6:]
                try:
                    data = SharedMemoryIPC.read_data(shm_name)
                except Exception as e:
                    logger.error("Failed to read from shared memory %s: %s", shm_name, e)
                    return
                finally:
                    SharedMemoryIPC.cleanup(shm_name)
            else:
                try:
                    if isinstance(sample.payload, bytes):
                        data = sample.payload
                    elif isinstance(sample.payload, str):
                        data = sample.payload.encode("utf-8")
                    else:
                        data = sample.payload.to_bytes()
                except Exception:
                    data = payload_str.encode("utf-8")

            # Execute callback
            res = on_chunk(data)
            if asyncio.iscoroutine(res) and self._loop is not None and self._loop.is_running():
                self._loop.call_soon_threadsafe(lambda: asyncio.create_task(res))

            # Send ACK capacity signal back to the sender
            self.send_ack()

        self.subscriber = self.zenoh_session.declare_subscriber(self.stream_topic, _on_sample)

    def stop(self) -> None:
        """Stop subscription and clean up."""
        if self.subscriber is not None:
            try:
                if hasattr(self.subscriber, "undeclare"):
                    self.subscriber.undeclare()  # type: ignore[no-untyped-call]
            except Exception as e:
                logger.debug("Failed to undeclare subscriber: %s", e)
            self.subscriber = None
