# Scheduler Roadmap

## Version 0.1

[x] Repository Foundation

[x] Node Models

[x] Node Registry

[x] Registration API

[x] Heartbeats

[x] Scheduling Algorithm

[x] Request Forwarding

[x] Multi-node Demonstration

[x] Concurrency Lock Migration (asyncio.Lock) & Concurrency Protection (Scheduling Dampener)

[x] RS256 JWT Ingress Router (`/api/v1/tasks/submit`) & Per-Tenant `TokenBucketLimiter` (Burst: 5, Refill: 1/2.0s, Overflow: HTTP 429)

[x] Two-Stage Capability Matchmaker Engine (Stage 1 Matrix: `backend`, `model_id`, `available_vram_bytes`, $\Delta t \le 15.0\text{s}$; Stage 2 Score: `(Reliability * 100.0) - (QueueDepth * 15.0) - (CPUUtilization * 0.5)`)

[x] Distributed Replicated State Consensus (`RaftConsensusEngine` over Zenoh)

[x] Verification Telemetry & Benchmark Alignment (REG-ORG-SYNC-003: 94 passing unit/integration tests, $15.05\text{s}$ stale node eviction boundary under $\Delta t > 15.0\text{s}$, 100% ruff/mypy compliance)

---

## Version 0.2

[ ] Persistent Registry

[ ] Adaptive Model Placement

[ ] Metrics

[ ] Dashboard

[ ] Health Monitoring

---

## Version 0.3

[ ] Geographic Scheduling

[ ] Fault Tolerance

[ ] Load Prediction

[ ] Intelligent Placement

---

## Version 1.0

[ ] Distributed AI Scheduler

[ ] Production Ready