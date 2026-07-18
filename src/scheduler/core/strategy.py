"""Abstract base class definition for scheduling strategies."""

from abc import ABC, abstractmethod
from typing import Any

from scheduler.models.node import Node


class SchedulingStrategy(ABC):
    """Abstract interface defining the two-stage scheduling strategy."""

    @abstractmethod
    def filter_nodes(
        self, task_requirements: dict[str, Any], live_nodes: list[Node]
    ) -> list[Node]:
        """Filter live nodes based on hard requirements (e.g. model support, VRAM).

        Args:
            task_requirements: Dict of hard constraints (VRAM, backend, model).
            live_nodes: List of registered compute nodes.

        Returns:
            List of nodes satisfying the hard requirements.
        """
        pass

    @abstractmethod
    def score_nodes(
        self, task: dict[str, Any], eligible_nodes: list[Node]
    ) -> list[tuple[Node, float]]:
        """Score eligible nodes based on dynamic load and historical metrics.

        Args:
            task: Task details.
            eligible_nodes: Subset of nodes that passed the filtering stage.

        Returns:
            A list of (Node, score) tuples, sorted by fitness score descending.
        """
        pass
