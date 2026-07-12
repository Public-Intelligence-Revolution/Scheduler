"""Heartbeat model for compute nodes in the scheduler."""

from datetime import datetime

from pydantic import BaseModel, Field

from scheduler.models.node import NodeStatus


class Heartbeat(BaseModel):
    """Representation of a compute node heartbeat message.

    Contains dynamic runtime status, load information, and
    resource utilization metrics.
    """

    node_id: str = Field(description="Unique identifier of the sending node")
    timestamp: datetime = Field(description="Timestamp of the heartbeat")
    status: NodeStatus = Field(description="Current status of the node")
    queue_length: int = Field(ge=0, description="Current length of the request queue")
    cpu_utilization: float = Field(
        ge=0.0, le=100.0, description="Current CPU utilization percentage (0.0 - 100.0)"
    )
    ram_available_gb: float = Field(ge=0.0, description="Available RAM in gigabytes")
    gpu_utilization: float = Field(
        ge=0.0, le=100.0, description="Current GPU utilization percentage (0.0 - 100.0)"
    )
    vram_available_gb: float = Field(ge=0.0, description="Available VRAM in gigabytes")
