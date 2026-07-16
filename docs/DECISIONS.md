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

## Node & Heartbeat Models

StrEnum for NodeStatus (Python 3.11+ native support).

Pydantic v2 BaseModel for GPUInfo, Node, and Heartbeat.

Separation of concerns: Node represents static configuration and identity, while Heartbeat represents runtime resource utilization and load metrics.

Pure data models with no business logic, storage, or networking.

Field-level validation constraints (gt, ge, le) for numeric and utilization fields.


---

## Node Registry

asyncio.Lock for thread-safety and non-blocking operation.

Plain dict for insertion-order preservation (Python 3.7+ guaranteed).

No singleton pattern. No global state.

ValueError for duplicate registration, missing update, and missing unregister.

---

## Registration API

NodeRegistry created in create_app() and stored on app.state.

FastAPI dependency injection via Annotated[type, Depends()] to satisfy ruff B008.

Thin handlers: API layer only translates HTTP to registry calls.

ValueError from registry mapped to HTTP 409. None from get mapped to HTTP 404.

---

## Heartbeat API & Updates

Heartbeat updates tracked in a separate `_heartbeats` dictionary in the registry, keyed by `node_id`.

`ValueError` raised when receiving a heartbeat from an unregistered node.

`POST /heartbeat` mapped to `NodeRegistry.update_heartbeat`. Mapped ValueError to HTTP 404 (Not Found) for unrecognized node_id.

---

## Scheduling Algorithm

Pure python implementation of scoring and selection logic decoupled from networking/HTTP layers.

Stable tie-breaking achieved using Python's `min()` which naturally preserves registry insertion order (stable sort).

Scoring parameters weighted according to: queue length (40%), GPU utilization (30%), CPU utilization (10%), and VRAM availability (20%). Uses normalized range-bound values to prevent metric skew.

Incremental scheduling dampener (+0.1 penalty per active assignment) is tracked and automatically applied/decayed to prevent the herd effect during concurrent bursts.

---

## Inference Request API

`POST /schedule` thin endpoint translating requests to `Scheduler.select_node`.

Uses FastAPI dependency injection to create and resolve `Scheduler` dependency dynamically using the shared `NodeRegistry`.

Maps ValueError to HTTP 404 (Not Found) when no eligible compute node is found.

---

## Interactive Scheduler Demonstration

Command line demonstration script `examples/demo.py` designed to run in a standalone fashion without spinning up web server.

Shows realistic distributed scenarios (e.g. A100 vs 4090 vs 3090) and step-by-step scoring transparency to validate correct algorithmic operation.

---

## Version 1 Scope

No Tensor Parallelism.

No Distributed KV Cache.

No Adaptive Scheduling.

No Geographic Scheduling.

These belong to future versions.
