"""Multi-agent engine schemas and data models."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class AgentRole(StrEnum):
    """Execution roles for autonomous sub-agents."""

    ORCHESTRATOR = "ORCHESTRATOR"
    ARCHITECT = "ARCHITECT"
    CODER = "CODER"
    AUDITOR = "AUDITOR"
    VERIFIER = "VERIFIER"


class SubTask(BaseModel):
    """Sub-task definition for sub-agent execution."""

    task_id: str
    role: AgentRole
    description: str
    dependencies: list[str] = Field(default_factory=list)
    depth: int = 0
    payload: dict[str, Any] = Field(default_factory=dict)


class SharedStateDelta(BaseModel):
    """Atomic state mutation returned by an isolated sub-agent worker."""

    task_id: str
    file_changes: dict[str, str] = Field(default_factory=dict)
    status_updates: dict[str, str] = Field(default_factory=dict)
    extracted_invariants: list[str] = Field(default_factory=list)
    error: str | None = None
    completed: bool = True


class SharedState(BaseModel):
    """Shared state container across all sub-agents."""

    files: dict[str, str] = Field(default_factory=dict)
    status: dict[str, str] = Field(default_factory=dict)
    invariants: list[str] = Field(default_factory=list)

    def snapshot(self) -> "SharedState":
        """Return a deep read-only state snapshot for worker isolation."""
        return SharedState(
            files=dict(self.files),
            status=dict(self.status),
            invariants=list(self.invariants),
        )
