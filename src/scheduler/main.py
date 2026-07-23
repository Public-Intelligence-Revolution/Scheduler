"""FastAPI application factory and lifespan management."""

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
import zenoh
from fastapi import FastAPI

from scheduler import __version__
from scheduler.api.health import router as health_router
from scheduler.api.heartbeat import router as heartbeat_router
from scheduler.api.ingress import router as ingress_router
from scheduler.api.nodes import router as nodes_router
from scheduler.api.schedule import router as schedule_router
from scheduler.core.config import get_settings
from scheduler.core.logging import setup_logging
from scheduler.core.rate_limiter import TokenBucketLimiter
from scheduler.core.zenoh_router import ZenohRouter
from scheduler.registry.node_registry import NodeRegistry

logger = structlog.stdlib.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown hooks."""
    settings = get_settings()
    setup_logging(settings.log_level)

    logger.info(
        "scheduler_started",
        version=__version__,
        environment=settings.environment.value,
    )

    # Initialize and start ZenohRouter
    zenoh_config = zenoh.Config()
    if settings.zenoh_listen_endpoints:
        zenoh_config.insert_json5("listen/endpoints", json.dumps(settings.zenoh_listen_endpoints))
        zenoh_config.insert_json5("mode", '"router"')
    if settings.zenoh_peer_endpoints:
        zenoh_config.insert_json5("connect/endpoints", json.dumps(settings.zenoh_peer_endpoints))
    if not settings.zenoh_multicast_scouting:
        zenoh_config.insert_json5("scouting/multicast/enabled", "false")

    zenoh_router = ZenohRouter(app.state.registry, config=zenoh_config)
    zenoh_router.start()
    app.state.zenoh_router = zenoh_router

    yield

    # Stop ZenohRouter on shutdown
    if hasattr(app.state, "zenoh_router"):
        app.state.zenoh_router.stop()

    logger.info("scheduler_stopped")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Public Intelligence Scheduler",
        description="Control plane for distributed AI infrastructure",
        version=__version__,
        lifespan=lifespan,
    )

    app.state.registry = NodeRegistry()
    app.state.rate_limiter = TokenBucketLimiter()

    from scheduler.core.engine import SchedulingEngine
    from scheduler.core.matchmaker import CapabilityMatchmaker

    strategy = CapabilityMatchmaker(app.state.registry)
    app.state.scheduling_engine = SchedulingEngine(app.state.registry, strategy)

    app.include_router(health_router)
    app.include_router(nodes_router)
    app.include_router(heartbeat_router)
    app.include_router(schedule_router)
    app.include_router(ingress_router)

    return app


app = create_app()
