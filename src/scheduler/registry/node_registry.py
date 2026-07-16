"""In-memory node registry for storing and managing compute nodes."""

import asyncio

from scheduler.models.heartbeat import Heartbeat
from scheduler.models.node import Node


class NodeRegistry:
    """Thread-safe in-memory registry of compute nodes.

    Stores Node objects keyed by node_id in insertion order.
    Also tracks runtime Heartbeat state for each node.
    Provides CRUD operations for node management.
    Contains no scheduler logic, persistence, or networking.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._nodes: dict[str, Node] = {}
        self._heartbeats: dict[str, Heartbeat] = {}
        self._dampeners: dict[str, float] = {}

    async def register(self, node: Node) -> None:
        """Register a new node.

        Args:
            node: The node to register.

        Raises:
            ValueError: If a node with the same node_id is already registered.
        """
        async with self._lock:
            if node.node_id in self._nodes:
                msg = f"Node already registered: {node.node_id}"
                raise ValueError(msg)
            self._nodes[node.node_id] = node
            self._dampeners[node.node_id] = 0.0

    async def unregister(self, node_id: str) -> None:
        """Remove a node and its heartbeat from the registry.

        Args:
            node_id: The ID of the node to remove.

        Raises:
            ValueError: If the node_id is not registered.
        """
        async with self._lock:
            if node_id not in self._nodes:
                msg = f"Node not found: {node_id}"
                raise ValueError(msg)
            del self._nodes[node_id]
            self._heartbeats.pop(node_id, None)
            self._dampeners.pop(node_id, None)

    async def get(self, node_id: str) -> Node | None:
        """Look up a node by ID.

        Args:
            node_id: The ID of the node to retrieve.

        Returns:
            The Node if found, otherwise None.
        """
        async with self._lock:
            return self._nodes.get(node_id)

    async def list(self) -> list[Node]:
        """Return all registered nodes in insertion order.

        Returns:
            A list of all registered Node objects.
        """
        async with self._lock:
            return list(self._nodes.values())

    async def update(self, node: Node) -> None:
        """Update an existing node's data.

        Args:
            node: The updated node. Must have a node_id that is already registered.

        Raises:
            ValueError: If the node_id is not registered.
        """
        async with self._lock:
            if node.node_id not in self._nodes:
                msg = f"Node not found: {node.node_id}"
                raise ValueError(msg)
            self._nodes[node.node_id] = node

    async def exists(self, node_id: str) -> bool:
        """Check whether a node is registered.

        Args:
            node_id: The ID to check.

        Returns:
            True if the node is registered, False otherwise.
        """
        async with self._lock:
            return node_id in self._nodes

    async def clear(self) -> None:
        """Remove all nodes and heartbeats from the registry."""
        async with self._lock:
            self._nodes.clear()
            self._heartbeats.clear()
            self._dampeners.clear()

    async def count(self) -> int:
        """Return the number of registered nodes.

        Returns:
            The count of registered nodes.
        """
        async with self._lock:
            return len(self._nodes)

    async def update_heartbeat(self, heartbeat: Heartbeat) -> None:
        """Update the runtime state for a registered node with a new heartbeat.

        Args:
            heartbeat: The heartbeat containing runtime metrics.

        Raises:
            ValueError: If the node_id in heartbeat is not registered.
        """
        async with self._lock:
            if heartbeat.node_id not in self._nodes:
                msg = f"Node not found: {heartbeat.node_id}"
                raise ValueError(msg)
            self._heartbeats[heartbeat.node_id] = heartbeat
            # Decay cleanly on incoming heartbeat
            self._dampeners[heartbeat.node_id] = 0.0

    async def get_heartbeat(self, node_id: str) -> Heartbeat | None:
        """Get the latest heartbeat for a node.

        Args:
            node_id: The ID of the node.

        Returns:
            The Heartbeat if found, otherwise None.
        """
        async with self._lock:
            return self._heartbeats.get(node_id)

    async def get_dampener(self, node_id: str) -> float:
        """Get the scheduling dampener for a node.

        Args:
            node_id: The ID of the node.

        Returns:
            The dampener value.
        """
        async with self._lock:
            return self._dampeners.get(node_id, 0.0)

    async def increment_dampener(self, node_id: str) -> None:
        """Increment the scheduling dampener for a node by 0.1.

        Args:
            node_id: The ID of the node.

        Raises:
            ValueError: If the node_id is not registered.
        """
        async with self._lock:
            if node_id not in self._nodes:
                msg = f"Node not found: {node_id}"
                raise ValueError(msg)
            self._dampeners[node_id] = self._dampeners.get(node_id, 0.0) + 0.1

    async def unregister_node(self, node_id: str) -> None:
        """Unregister a node and clear its dynamic herd dampeners.

        This method is idempotent and does not raise an error if the node
        is not found, allowing clean self-correcting pool resize operations.

        Args:
            node_id: The ID of the node to unregister.
        """
        async with self._lock:
            self._nodes.pop(node_id, None)
            self._heartbeats.pop(node_id, None)
            self._dampeners.pop(node_id, None)
