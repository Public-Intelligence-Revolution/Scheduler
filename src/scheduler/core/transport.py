"""Transport layer implementing SharedMemory IPC and Backpressured WAN routing on Scheduler."""

import json
import uuid
from multiprocessing import shared_memory

import zenoh


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
        except Exception:
            pass


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

    def send_ack(self) -> None:
        """Publish a processing capacity signal (ACK) back to the stream router."""
        self.processed_count += 1
        payload = json.dumps({"seq": self.processed_count})
        self.zenoh_session.put(self.ack_topic, payload)
