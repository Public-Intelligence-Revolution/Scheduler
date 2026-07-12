"""FastAPI application factory and lifespan management."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from scheduler import __version__
from scheduler.api.health import router as health_router
from scheduler.api.nodes import router as nodes_router
from scheduler.core.config import get_settings
from scheduler.core.logging import setup_logging
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
    yield
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

    app.include_router(health_router)
    app.include_router(nodes_router)

    return app


app = create_app()
