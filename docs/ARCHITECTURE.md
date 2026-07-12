# Scheduler Architecture

## Purpose

The Scheduler is the control plane of Public Intelligence.

It receives inference requests, determines the most appropriate compute node, forwards the request, and returns the response.

The Scheduler does NOT execute AI models.

The Scheduler does NOT perform distributed inference.

Its only responsibility is intelligent request routing.

---

## Responsibilities

- Maintain knowledge of available nodes
- Track node health
- Track node capabilities
- Select the best node
- Forward requests
- Return responses

---

## Current Architecture

Client

↓

Scheduler (FastAPI)

↓

Node Registry

↓

Scheduler Algorithm

↓

Compute Node

↓

LLM

↓

Scheduler

↓

Client

---

## Data Models

### NodeStatus

Enum (StrEnum) representing node operational state: ONLINE, OFFLINE, BUSY, UNKNOWN.

### GPUInfo

Pydantic model for GPU hardware: name, vram_total_gb, vram_available_gb.

### Node

Pydantic model representing static compute node identity and capabilities: identity (node_id, hostname, ip_address, region), hardware (gpu, cpu_cores, ram_total_gb), and available_models.

Defined in src/scheduler/models/node.py. Exported from src/scheduler/models/__init__.py.

### Heartbeat

Pydantic model representing dynamic runtime status and resource utilization of a compute node: node_id, timestamp, status, queue_length, cpu_utilization, ram_available_gb, gpu_utilization, vram_available_gb.

Defined in src/scheduler/models/heartbeat.py. Exported from src/scheduler/models/__init__.py.


---

## Node Registry

### NodeRegistry

Thread-safe in-memory registry storing Node objects keyed by node_id. Preserves insertion order. Tracks runtime Heartbeat updates. Provides register, unregister, get, list, update, exists, clear, count, update_heartbeat, and get_heartbeat operations.

Raises ValueError on duplicate registration, updating a missing node, removing a missing node, or updating a heartbeat for an unregistered node.

Contains no scheduler logic, persistence, networking, or HTTP endpoints.

Defined in src/scheduler/registry/node_registry.py. Exported from src/scheduler/registry/__init__.py.

---

## Registration API

Thin API layer translating HTTP requests to NodeRegistry operations.

Endpoints: POST /nodes/register, GET /nodes, GET /nodes/{node_id}.

NodeRegistry is created in create_app() and stored on app.state. Retrieved via FastAPI dependency injection using Annotated[NodeRegistry, Depends(get_registry)].

Handlers contain no business logic. The registry is solely responsible for node management.

Defined in src/scheduler/api/nodes.py. Mounted in src/scheduler/main.py.

---

## Heartbeat API

Thin API layer receiving compute node heartbeats.

Endpoint: POST /heartbeat.

Uses NodeRegistry to store the latest heartbeat metrics for the reporting node. Maps NodeRegistry ValueErrors to HTTP 404 (Not Found) when the node is unknown.

Defined in src/scheduler/api/heartbeat.py. Mounted in src/scheduler/main.py.

---

## Scheduling Algorithm

### Scheduler

Deterministic compute node selection logic based on node capacity, status, and resource load.

Retrieves registered nodes from the registry and filters them to identify eligible candidate nodes. Candidate nodes must:
- Advertise the requested model in `available_models`.
- Have an active runtime heartbeat record.
- Have a status other than `OFFLINE`.

Scores eligible candidate nodes using the formula:
`score = (queue_length * 0.5) + (gpu_utilization * 0.3) + (cpu_utilization * 0.1) - (vram_available_gb * 0.1)`

Selects and returns the node with the lowest score. Ties are broken deterministically by selecting the first node in insertion order. Raises a `ValueError` if no eligible nodes are found.

Defined in src/scheduler/scheduler/algorithm.py. Exported from src/scheduler/scheduler/__init__.py.

---

## Inference Request API

Thin endpoint exposing the scheduling capabilities to clients.

Endpoint: POST /schedule.

Accepts a model request (`ScheduleRequest`) and invokes the `Scheduler` algorithm via dependency injection. Returns a `ScheduleResponse` containing node credentials on success, or raises HTTP 404 (Not Found) if no eligible nodes are found.

Defined in src/scheduler/api/schedule.py. Mounted in src/scheduler/main.py.

---

## Out of Scope (v1)

- Tensor Parallelism
- Pipeline Parallelism
- Geographic Scheduling
- Adaptive Model Placement
- Authentication
- Persistent Database
- Metrics Dashboard
- Distributed KV Cache

---

## Future

Future versions will introduce adaptive scheduling, intelligent model placement, distributed inference, and geographically aware routing.