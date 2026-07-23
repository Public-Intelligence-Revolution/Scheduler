"""MultiAgentOrchestrator for managing isolated sub-agents."""

import asyncio
from collections.abc import Callable
from typing import Any

from scheduler.agent.schema import SharedState, SharedStateDelta, SubTask
from scheduler.agent.worker import WorkerContext


class MultiAgentOrchestrator:
    """Orchestrates parallel worker sub-tasks with strict atomic state updates."""

    def __init__(
        self,
        max_workers: int = 4,
        max_depth: int = 3,
        task_timeout: float = 30.0,
    ) -> None:
        self.max_workers = max_workers
        self.max_depth = max_depth
        self.task_timeout = task_timeout
        self.state = SharedState()
        self._lock = asyncio.Lock()

    async def apply_delta(self, delta: SharedStateDelta) -> SharedState:
        r"""Atomically merge state delta into shared state."""
        async with self._lock:
            # Merge file changes
            self.state.files.update(delta.file_changes)
            # Merge status updates
            self.state.status.update(delta.status_updates)
            # Merge extracted invariants maintaining uniqueness
            for inv in delta.extracted_invariants:
                if inv not in self.state.invariants:
                    self.state.invariants.append(inv)
            return self.state.snapshot()

    async def get_state_snapshot(self) -> SharedState:
        """Get thread-safe read-only snapshot of current shared state."""
        async with self._lock:
            return self.state.snapshot()

    async def execute_task(
        self,
        task: SubTask,
        handler: Callable[[SubTask, SharedState], Any] | None = None,
    ) -> SharedStateDelta:
        """Execute a single sub-task using WorkerContext within bounds."""
        if task.depth > self.max_depth:
            delta = SharedStateDelta(
                task_id=task.task_id,
                error=f"Exceeded max recursion depth of {self.max_depth}",
                completed=False,
            )
            await self.apply_delta(delta)
            return delta

        snapshot = await self.get_state_snapshot()
        worker = WorkerContext(task=task, read_only_state=snapshot, handler=handler)

        try:
            delta = await asyncio.wait_for(worker.execute(), timeout=self.task_timeout)
        except TimeoutError:
            delta = SharedStateDelta(
                task_id=task.task_id,
                error=f"Task timed out after {self.task_timeout}s",
                completed=False,
            )

        await self.apply_delta(delta)
        return delta

    async def run_batch(
        self,
        tasks: list[SubTask],
        handlers: dict[str, Callable[[SubTask, SharedState], Any]] | None = None,
    ) -> list[SharedStateDelta]:
        """Run a set of sub-tasks subject to dependency resolution and limits."""
        handlers = handlers or {}
        completed_tasks: set[str] = set()
        pending_tasks = list(tasks)
        results: list[SharedStateDelta] = []
        semaphore = asyncio.Semaphore(self.max_workers)

        async def worker_wrapper(t: SubTask) -> SharedStateDelta:
            async with semaphore:
                h = handlers.get(t.task_id) or handlers.get(t.role.value)
                return await self.execute_task(t, handler=h)

        while pending_tasks:
            # Find tasks whose dependencies are satisfied
            ready_tasks = [
                t for t in pending_tasks if all(dep in completed_tasks for dep in t.dependencies)
            ]

            if not ready_tasks:
                # Circular dependency or missing dependency deadlock safeguard
                for t in pending_tasks:
                    err_delta = SharedStateDelta(
                        task_id=t.task_id,
                        error=f"Unresolved dependencies: {t.dependencies}",
                        completed=False,
                    )
                    await self.apply_delta(err_delta)
                    results.append(err_delta)
                break

            # Process ready tasks concurrently up to concurrency limit
            batch_results = await asyncio.gather(*(worker_wrapper(t) for t in ready_tasks))

            for t, res in zip(ready_tasks, batch_results, strict=False):
                results.append(res)
                if res.completed and not res.error:
                    completed_tasks.add(t.task_id)
                pending_tasks.remove(t)

        return results
