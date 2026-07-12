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