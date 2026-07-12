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

Request body: Heartbeat

Returns: {"status": "ok"} (HTTP 200 OK)

If the node is not registered, returns HTTP 404 Not Found.

---

## Planned APIs

POST /schedule

Return the best node for a request.

---

POST /forward

Forward inference request to selected node.