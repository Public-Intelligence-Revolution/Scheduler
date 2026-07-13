# Public Intelligence Scheduler

The Scheduler is the decision engine of the Public Intelligence network.

It maintains a registry of available compute nodes, receives periodic heartbeats, and selects the most appropriate node for inference requests.

Version 1 focuses on building the core scheduling infrastructure.

---

## Demo

A walkthrough of the first working prototype is available on YouTube:
[Public Intelligence v1 Demo](https://www.youtube.com/watch?v=cGDWpOArB5I)

This video demonstrates the end-to-end integration of the Website, Scheduler (showing the current v1 implementation), Node, registration, heartbeats, and local inference.

---

## Current Features

- Node registration
- Node unregistration
- Heartbeat processing
- In-memory node registry
- Deterministic scheduling algorithm
- REST API
- End-to-end demonstration
- Comprehensive test suite

---

## Architecture

```text
               Client

                  │

                  ▼

            Scheduler API

                  │

                  ▼

          Scheduling Algorithm

                  │

                  ▼

            Node Registry

                  ▲

      Registration / Heartbeats

                  │

                  ▼

                 Nodes
```

---

## Running

```bash
python -m scheduler.main
```

or

```bash
uvicorn scheduler.main:app --reload
```

---

## Version

Current Release

```
v1.0.0
```

---

## Roadmap

Version 2 will introduce:

- Request orchestration
- Automatic request forwarding
- Failure recovery
- Retry logic
- Multi-node inference routing

---

## Related Repositories

- Public Intelligence Website
- Public Intelligence Node

---

## License

Apache 2.0