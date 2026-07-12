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

Pydantic model representing a compute node: identity (node_id, hostname, ip_address, region), hardware (gpu, cpu_cores, ram_gb), state (models, queue_length, status, last_heartbeat).

Defined in src/scheduler/models/node.py. Exported from src/scheduler/models/__init__.py.

---

## Node Registry

### NodeRegistry

Thread-safe in-memory registry storing Node objects keyed by node_id. Preserves insertion order. Provides register, unregister, get, list, update, exists, clear, and count operations.

Raises ValueError on duplicate registration, updating a missing node, or removing a missing node.

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