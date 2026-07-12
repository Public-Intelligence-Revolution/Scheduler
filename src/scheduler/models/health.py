"""Health check response models."""

from datetime import datetime

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Liveness probe response."""

    status: str = Field(description="Service status")
    version: str = Field(description="Application version")
    environment: str = Field(description="Deployment environment")


class ReadinessResponse(BaseModel):
    """Readiness probe response."""

    status: str = Field(description="Service status")
    version: str = Field(description="Application version")
    environment: str = Field(description="Deployment environment")
    uptime_seconds: float = Field(description="Seconds since service start")
    timestamp: datetime = Field(description="Current server timestamp")
