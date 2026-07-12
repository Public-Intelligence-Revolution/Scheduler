# Engineering Decisions

## Repository

Python >=3.11

FastAPI

Pydantic v2

Structured Logging (structlog)

Docker

Hatchling build system

---

## Development Philosophy

Small features.

One feature.

One commit.

Every feature must build successfully before continuing.

Every feature must pass Ruff, Mypy, and Pytest.

---

## Scheduler Philosophy

The Scheduler never performs inference.

Nodes perform inference.

The Scheduler only decides where requests should execute.

---

## Node Models

StrEnum for NodeStatus (Python 3.11+ native support).

Pydantic v2 BaseModel for GPUInfo and Node.

Pure data models with no business logic, storage, or networking.

Field-level validation constraints (gt, ge) for numeric fields.

---

## Node Registry

threading.Lock for thread-safety (standard library only).

Plain dict for insertion-order preservation (Python 3.7+ guaranteed).

No singleton pattern. No global state.

ValueError for duplicate registration, missing update, and missing unregister.

---

## Version 1 Scope

No Tensor Parallelism.

No Distributed KV Cache.

No Adaptive Scheduling.

No Geographic Scheduling.

These belong to future versions.
