"""Orchestration engine for multi-stage scheduling."""

import hashlib
import uuid
from typing import Any

from scheduler.core.strategy import SchedulingStrategy
from scheduler.registry.node_registry import NodeRegistry


class SchedulingEngine:
    """Orchestration engine implementing two-stage node task scheduling."""

    def __init__(self, registry: NodeRegistry, strategy: SchedulingStrategy) -> None:
        """Initialize the SchedulingEngine.

        Args:
            registry: The active NodeRegistry instance.
            strategy: The SchedulingStrategy algorithm provider.
        """
        self.registry = registry
        self.strategy = strategy

    async def schedule_task(self, task: dict[str, Any]) -> tuple[str, str]:
        """Schedule an incoming task to the highest-scoring eligible node.

        Stages the task requirements through capability filtering and telemetry-based
        scoring, updates the node's tracked load, and generates a transaction hash.

        Args:
            task: Dict detailing the task parameters and requirements.

        Returns:
            A tuple of (transaction_hash, node_id).

        Raises:
            ValueError: If no active nodes satisfy the task hard constraints.
        """
        # 1. Retrieve all registered live nodes
        live_nodes = await self.registry.list()

        # 2. Stage 1: Filter nodes by hard requirements
        requirements = task.get("requirements", {})
        eligible_nodes = self.strategy.filter_nodes(requirements, live_nodes)

        if not eligible_nodes:
            raise ValueError("No active nodes satisfy the task requirements.")

        # 3. Stage 2: Score eligible nodes by current load
        ranked_nodes = self.strategy.score_nodes(task, eligible_nodes)
        selected_node, score = ranked_nodes[0]

        # 4. Update the inner state tracking registry (dynamic queue depth update)
        node_id = selected_node.node_id
        if node_id not in self.registry._telemetry:
            self.registry._telemetry[node_id] = {}

        current_q = self.registry._telemetry[node_id].get("queue_depth", 0)
        self.registry._telemetry[node_id]["queue_depth"] = current_q + 1

        # 5. Route the transaction hash out (SHA-256 of node_id + task_id + score)
        task_id = task.get("task_id", str(uuid.uuid4()))
        tx_raw = f"{node_id}:{task_id}:{score}"
        tx_hash = hashlib.sha256(tx_raw.encode("utf-8")).hexdigest()

        return tx_hash, node_id
