# Scheduler Agent Instructions

Read these documents before inspecting the repository:

1. docs/VISION.md
2. docs/ARCHITECTURE.md
3. docs/ROADMAP.md
4. docs/STATUS.md
5. docs/DECISIONS.md
6. docs/API.md

Development Rules

- Never redesign the architecture unless explicitly instructed.
- Never refactor unrelated code.
- Never modify more files than necessary.
- One feature = one implementation = one commit.
- Every implementation must pass Ruff, Mypy and Pytest before completion.
- Keep implementations simple.
- Do not introduce unnecessary abstractions.
- Scheduler v1 focuses only on request scheduling and forwarding.
- Distributed inference is out of scope.
- Tensor Parallelism is out of scope.
- Adaptive Model Placement is out of scope.
- Geographic Scheduling is out of scope.

Documentation Policy

- Documentation is part of the implementation.
- A feature is not complete until documentation is updated.
- Every completed feature must update docs/STATUS.md and docs/ROADMAP.md.
- Update docs/ARCHITECTURE.md if architecture changes.
- Update docs/API.md if APIs change.
- Update docs/DECISIONS.md if engineering decisions change.
- Update docs/VISION.md only if the long-term vision changes.
- Documentation must always match the current repository state.

Current Priority

Complete Scheduler Version 1 before implementing Version 2 features.

---

# Event Log

## 2026-07-16

### Changes Made
- Migrated `NodeRegistry` to use non-blocking native `asyncio.Lock` instead of standard `threading.Lock`.
- Made all `NodeRegistry` methods async and updated downstream routing endpoints (`register_node`, `list_nodes`, `get_node`, `receive_heartbeat`, `schedule_request`) to be `async def` and correctly await registry access.
- Rewrote the load equation inside `algorithm.py` using strictly normalized, range-bound metric weights to eliminate VRAM skew:
  `Score = (queue_length * 0.4) + (gpu_utilization_norm * 0.3) + (cpu_utilization_norm * 0.1) + ((1.0 - (vram_available / vram_total)) * 0.2)`
- Added a `scheduling_dampener` atomic tracker (+0.1 penalty increment per active task assignment) inside the node registry's node tracking state to prevent herd effect under concurrent bursts, decaying cleanly to 0.0 upon incoming `POST /heartbeat` metrics.
- Converted all tests in `tests/test_registry/test_node_registry.py` and `tests/test_scheduler/test_algorithm.py` to be async, substituting threading concurrency checks with asyncio gather/tasks and adding specific tests for scoring engine correctness and dampener functionality.

## 2026-07-17

### Changes Made
- Added `eclipse-zenoh` core transport dependency to support peer-to-peer node heartbeats.
- Created `ZenohRouter` class inside `src/scheduler/core/zenoh_router.py` to bind an asynchronous Zenoh session listening on the key expression `public-intelligence/net/*/heartbeat`.
- Decoded Zenoh payloads safely and routed heartbeat updates directly into the non-blocking `NodeRegistry`, preserving the score and dampener invariants.
- Configured FastAPI startup lifespan to launch and manage the `ZenohRouter` background subscriber.
- Wrote integration tests in `tests/test_zenoh_integration.py` simulating a Node publishing metrics over a local Zenoh session and verifying `NodeRegistry` state changes.
- Added `unregister_node(node_id)` safe idempotent method to `NodeRegistry` to unregister nodes and clear all metrics/herd dampeners safely on deathrattles.
- Declared Zenoh Liveliness subscriber monitoring `public-intelligence/net/liveliness/*` on `ZenohRouter` startup.
- Processed DELETE events (deathrattles) in `ZenohRouter` callback to unregister dropped nodes from `NodeRegistry` asynchronously.
- Wrote integration tests in `tests/test_zenoh_integration.py` (`test_zenoh_liveliness_deathrattle`) simulating node session drops and asserting automatic registry unregistration.
- Implemented `RaftConsensusEngine` in `src/scheduler/core/consensus.py` running a lightweight Raft consensus loop over Zenoh channels.
- Intercepted `register`, `unregister`, and `unregister_node` mutations in `NodeRegistry` to propose them through consensus, waiting for majority quorum before applying locally.
- Integrated consensus engine start/stop lifecycle into `ZenohRouter`.
- Added integration test suite in `tests/test_consensus.py` simulating 3 schedulers, checking leader election, log replication, and minority partition blocking.

### Metrics Achieved
- Verification suite (Ruff, MyPy src/tests, PyTest) passes with 100% success (0 errors, 83/83 unit & integration tests passing).

### Next Priority Items
- Persistent Registry integration (Phase 0.2)
- Adaptive Model Placement