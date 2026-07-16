"""Scheduling algorithm for compute node selection."""

from scheduler.models.node import Node, NodeStatus
from scheduler.registry.node_registry import NodeRegistry


class Scheduler:
    """Deterministic scheduler for compute node selection.

    Selects the best eligible compute node for a requested model
    based on resource utilization and queue length.
    """

    def __init__(self, registry: NodeRegistry) -> None:
        """Initialize the scheduler with a node registry.

        Args:
            registry: The node registry to query.
        """
        self._registry = registry

    async def select_node(self, model_name: str) -> Node:
        """Select the best compute node for the requested model.

        Filters nodes by registration status, active heartbeat, status (must
        not be OFFLINE), and model availability. Scores remaining nodes
        and returns the one with the lowest score. Ties are broken by
        insertion order.

        Args:
            model_name: The name of the requested AI model.

        Returns:
            The selected Node object.

        Raises:
            ValueError: If no eligible node is found.
        """
        nodes = await self._registry.list()
        eligible_nodes_with_scores: list[tuple[Node, float]] = []

        for node in nodes:
            # 1. Must advertise the requested model
            if model_name not in node.available_models:
                continue

            # 2. Must have a heartbeat
            heartbeat = await self._registry.get_heartbeat(node.node_id)
            if heartbeat is None:
                continue

            # 3. Must not be OFFLINE
            if heartbeat.status == NodeStatus.OFFLINE:
                continue

            # Get dampener
            dampener = await self._registry.get_dampener(node.node_id)

            # Compute score
            # Score = (queue_length * 0.4) + (gpu_utilization * 0.3)
            #         + (cpu_utilization * 0.1)
            #         + ((1.0 - (vram_available / vram_total)) * 0.2) + dampener
            gpu_util = heartbeat.gpu_utilization / 100.0
            cpu_util = heartbeat.cpu_utilization / 100.0
            vram_total = node.gpu.vram_total_gb
            vram_ratio = heartbeat.vram_available_gb / vram_total if vram_total > 0 else 0.0

            score = (
                (heartbeat.queue_length * 0.4)
                + (gpu_util * 0.3)
                + (cpu_util * 0.1)
                + ((1.0 - vram_ratio) * 0.2)
                + dampener
            )
            eligible_nodes_with_scores.append((node, score))

        if not eligible_nodes_with_scores:
            msg = f"No eligible nodes found for model: {model_name}"
            raise ValueError(msg)

        # Stable min: Python's min is stable, so in case of ties it returns
        # the first node in insertion order (which is preserved in self._registry.list()).
        selected_node, _ = min(eligible_nodes_with_scores, key=lambda x: x[1])

        # Increment scheduling dampener by 0.1 for active task assignment
        await self._registry.increment_dampener(selected_node.node_id)

        return selected_node
