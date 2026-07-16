# Scheduler API

## Health

GET /health

Returns scheduler liveness.

---

GET /health/ready

Returns scheduler readiness.

---

## Nodes

POST /nodes/register

Register a compute node.

Headers:
- `X-Network-Auth-Token`: The secure network authentication token (required if configured)

Request body: Node

Returns: Node (HTTP 201 Created)

Duplicate node_id returns HTTP 409 Conflict.

---

GET /nodes

List all registered nodes.

Returns: list[Node] (HTTP 200)

---

GET /nodes/{node_id}

Get a specific node by ID.

Returns: Node (HTTP 200)

Missing node returns HTTP 404.

---

## Heartbeat

POST /heartbeat

Update node runtime status and resource utilization metrics.

Headers:
- `X-Network-Auth-Token`: The secure network authentication token (required if configured)

Request body: Heartbeat

Returns: {"status": "ok"} (HTTP 200 OK)

If the node is not registered, returns HTTP 404 Not Found.

---

## Schedule

POST /schedule

Find the best eligible compute node for running a requested model.

Headers:
- `X-Network-Auth-Token`: The secure network authentication token (required if configured)

Request body: ScheduleRequest (with field model_name: str)

Returns: ScheduleResponse (with fields node_id, hostname, ip_address, region) (HTTP 200 OK)

If no eligible node is found or registered, returns HTTP 404 Not Found.

---

## Planned APIs

POST /forward

Forward inference request to selected node.