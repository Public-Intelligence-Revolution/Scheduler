"""Health and readiness probe endpoints."""

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from scheduler import __version__
from scheduler.core.config import Settings, get_settings
from scheduler.models.health import HealthResponse, ReadinessResponse

router = APIRouter(tags=["health"])

_start_time: float = time.monotonic()


@router.get("/health", response_model=HealthResponse)
async def health(
    settings: Settings = Depends(get_settings),
) -> HealthResponse:
    """Liveness probe. Returns 200 if the process is running."""
    return HealthResponse(
        status="healthy",
        version=__version__,
        environment=settings.environment.value,
    )


@router.get("/health/ready", response_model=ReadinessResponse)
async def readiness(
    settings: Settings = Depends(get_settings),
) -> ReadinessResponse:
    """Readiness probe. Returns 200 when the service can accept traffic."""
    return ReadinessResponse(
        status="ready",
        version=__version__,
        environment=settings.environment.value,
        uptime_seconds=time.monotonic() - _start_time,
        timestamp=datetime.now(tz=timezone.utc),
    )
