# Scheduler API

## Health

GET /health

Returns scheduler liveness.

---

GET /health/ready

Returns scheduler readiness.

---

## Planned APIs

POST /nodes/register

Register a compute node.

---

POST /heartbeat

Update node status.

---

GET /nodes

List registered nodes.

---

POST /schedule

Return the best node for a request.

---

POST /forward

Forward inference request to selected node.