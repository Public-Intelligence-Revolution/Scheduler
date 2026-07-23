"""Unit tests for multi-agent engine in Scheduler."""

import asyncio

import pytest

from scheduler.agent.orchestrator import MultiAgentOrchestrator
from scheduler.agent.schema import AgentRole, SharedState, SharedStateDelta, SubTask


@pytest.mark.asyncio
async def test_atomic_state_merge() -> None:
    """Verify atomic state updates with apply_delta."""
    orchestrator = MultiAgentOrchestrator()
    delta1 = SharedStateDelta(
        task_id="t1",
        file_changes={"a.py": "print('hello')"},
        status_updates={"t1": "COMPLETED"},
        extracted_invariants=["inv1"],
    )
    delta2 = SharedStateDelta(
        task_id="t2",
        file_changes={"b.py": "print('world')"},
        status_updates={"t2": "COMPLETED"},
        extracted_invariants=["inv1", "inv2"],
    )

    await orchestrator.apply_delta(delta1)
    state = await orchestrator.apply_delta(delta2)

    assert state.files == {"a.py": "print('hello')", "b.py": "print('world')"}
    assert state.status == {"t1": "COMPLETED", "t2": "COMPLETED"}
    assert state.invariants == ["inv1", "inv2"]


@pytest.mark.asyncio
async def test_parallel_worker_execution() -> None:
    """Verify parallel execution of independent sub-tasks."""
    orchestrator = MultiAgentOrchestrator(max_workers=4)

    tasks = [
        SubTask(task_id=f"t_{i}", role=AgentRole.CODER, description=f"Task {i}") for i in range(4)
    ]

    async def custom_handler(task: SubTask, read_state: SharedState) -> SharedStateDelta:
        await asyncio.sleep(0.01)
        return SharedStateDelta(
            task_id=task.task_id,
            status_updates={task.task_id: "DONE"},
        )

    results = await orchestrator.run_batch(tasks, handlers={AgentRole.CODER.value: custom_handler})
    assert len(results) == 4
    snapshot = await orchestrator.get_state_snapshot()
    assert len(snapshot.status) == 4


@pytest.mark.asyncio
async def test_dependency_resolution() -> None:
    """Verify tasks execute in order based on declared dependencies."""
    orchestrator = MultiAgentOrchestrator()

    t1 = SubTask(task_id="t1", role=AgentRole.ARCHITECT, description="Design")
    t2 = SubTask(
        task_id="t2",
        role=AgentRole.CODER,
        description="Build",
        dependencies=["t1"],
    )

    execution_order: list[str] = []

    async def handler(task: SubTask, read_state: SharedState) -> SharedStateDelta:
        execution_order.append(task.task_id)
        return SharedStateDelta(
            task_id=task.task_id,
            status_updates={task.task_id: "DONE"},
        )

    results = await orchestrator.run_batch(
        [t2, t1],
        handlers={
            AgentRole.ARCHITECT.value: handler,
            AgentRole.CODER.value: handler,
        },
    )

    assert len(results) == 2
    assert execution_order == ["t1", "t2"]


@pytest.mark.asyncio
async def test_worker_error_isolation() -> None:
    """Verify worker exception is captured cleanly in SharedStateDelta."""
    orchestrator = MultiAgentOrchestrator()

    t1 = SubTask(task_id="t1", role=AgentRole.AUDITOR, description="Audit fail")

    async def failing_handler(task: SubTask, read_state: SharedState) -> SharedStateDelta:
        raise ValueError("Audit constraint violated!")

    results = await orchestrator.run_batch(
        [t1], handlers={AgentRole.AUDITOR.value: failing_handler}
    )

    assert len(results) == 1
    assert results[0].completed is False
    assert results[0].error == "Audit constraint violated!"


@pytest.mark.asyncio
async def test_max_depth_exceeded() -> None:
    """Verify tasks exceeding max depth return depth error."""
    orchestrator = MultiAgentOrchestrator(max_depth=3)
    t = SubTask(task_id="deep", role=AgentRole.VERIFIER, description="Deep task", depth=4)

    result = await orchestrator.execute_task(t)
    assert result.completed is False
    assert "Exceeded max recursion depth" in (result.error or "")
