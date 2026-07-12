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

## Planned APIs

POST /heartbeat

Update node status.

---

POST /schedule

Return the best node for a request.

---

POST /forward

Forward inference request to selected node.