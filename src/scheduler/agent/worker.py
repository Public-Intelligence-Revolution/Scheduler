"""WorkerContext running isolated task loops returning SharedStateDelta."""

import inspect
from collections.abc import Callable
from typing import Any

from scheduler.agent.schema import SharedState, SharedStateDelta, SubTask


class WorkerContext:
    """Isolated execution context for a single sub-agent worker."""

    def __init__(
        self,
        task: SubTask,
        read_only_state: SharedState,
        handler: Callable[[SubTask, SharedState], Any] | None = None,
    ) -> None:
        self.task = task
        self.read_only_state = read_only_state
        self.handler = handler

    async def execute(self) -> SharedStateDelta:
        """Run isolated task execution and return a SharedStateDelta."""
        if self.task.depth > 3:
            return SharedStateDelta(
                task_id=self.task.task_id,
                error=f"Exceeded max recursion depth (depth={self.task.depth})",
                completed=False,
            )

        try:
            if self.handler is not None:
                if inspect.iscoroutinefunction(self.handler):
                    delta = await self.handler(self.task, self.read_only_state)
                else:
                    delta = self.handler(self.task, self.read_only_state)
                if isinstance(delta, SharedStateDelta):
                    return delta

            # Default worker behavior
            return SharedStateDelta(
                task_id=self.task.task_id,
                status_updates={self.task.task_id: "COMPLETED"},
                completed=True,
            )
        except Exception as exc:
            return SharedStateDelta(
                task_id=self.task.task_id,
                error=str(exc),
                completed=False,
            )
