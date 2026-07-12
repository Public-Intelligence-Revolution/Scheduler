"""In-memory node registry for storing and managing compute nodes."""

import threading

from scheduler.models.node import Node


class NodeRegistry:
    """Thread-safe in-memory registry of compute nodes.

    Stores Node objects keyed by node_id in insertion order.
    Provides CRUD operations for node management.
    Contains no scheduler logic, persistence, or networking.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._nodes: dict[str, Node] = {}

    def register(self, node: Node) -> None:
        """Register a new node.

        Args:
            node: The node to register.

        Raises:
            ValueError: If a node with the same node_id is already registered.
        """
        with self._lock:
            if node.node_id in self._nodes:
                msg = f"Node already registered: {node.node_id}"
                raise ValueError(msg)
            self._nodes[node.node_id] = node

    def unregister(self, node_id: str) -> None:
        """Remove a node from the registry.

        Args:
            node_id: The ID of the node to remove.

        Raises:
            ValueError: If the node_id is not registered.
        """
        with self._lock:
            if node_id not in self._nodes:
                msg = f"Node not found: {node_id}"
                raise ValueError(msg)
            del self._nodes[node_id]

    def get(self, node_id: str) -> Node | None:
        """Look up a node by ID.

        Args:
            node_id: The ID of the node to retrieve.

        Returns:
            The Node if found, otherwise None.
        """
        with self._lock:
            return self._nodes.get(node_id)

    def list(self) -> list[Node]:
        """Return all registered nodes in insertion order.

        Returns:
            A list of all registered Node objects.
        """
        with self._lock:
            return list(self._nodes.values())

    def update(self, node: Node) -> None:
        """Update an existing node's data.

        Args:
            node: The updated node. Must have a node_id that is already registered.

        Raises:
            ValueError: If the node_id is not registered.
        """
        with self._lock:
            if node.node_id not in self._nodes:
                msg = f"Node not found: {node.node_id}"
                raise ValueError(msg)
            self._nodes[node.node_id] = node

    def exists(self, node_id: str) -> bool:
        """Check whether a node is registered.

        Args:
            node_id: The ID to check.

        Returns:
            True if the node is registered, False otherwise.
        """
        with self._lock:
            return node_id in self._nodes

    def clear(self) -> None:
        """Remove all nodes from the registry."""
        with self._lock:
            self._nodes.clear()

    def count(self) -> int:
        """Return the number of registered nodes.

        Returns:
            The count of registered nodes.
        """
        with self._lock:
            return len(self._nodes)
