"""Node representation models for compute nodes in the scheduler."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class NodeStatus(StrEnum):
    """Operational status of a compute node."""

    ONLINE = "online"
    OFFLINE = "offline"
    BUSY = "busy"
    UNKNOWN = "unknown"


class GPUInfo(BaseModel):
    """GPU hardware information for a compute node."""

    name: str = Field(description="GPU model name")
    vram_total_gb: float = Field(gt=0, description="Total VRAM in gigabytes")
    vram_available_gb: float = Field(ge=0, description="Available VRAM in gigabytes")


class Node(BaseModel):
    """Representation of a compute node in the scheduler network.

    Contains identity, hardware capabilities, loaded models,
    current load, and health status. This is a pure data model
    with no business logic, storage, or networking.
    """

    node_id: str = Field(description="Unique identifier for the node")
    hostname: str = Field(description="Node hostname")
    ip_address: str = Field(description="Node IP address")
    region: str = Field(description="Geographic region of the node")
    gpu: GPUInfo = Field(description="GPU hardware information")
    cpu_cores: int = Field(gt=0, description="Number of CPU cores")
    ram_gb: float = Field(gt=0, description="Total RAM in gigabytes")
    models: list[str] = Field(default_factory=list, description="Loaded model identifiers")
    queue_length: int = Field(default=0, ge=0, description="Current request queue length")
    status: NodeStatus = Field(default=NodeStatus.UNKNOWN, description="Current node status")
    last_heartbeat: datetime = Field(description="Timestamp of last heartbeat")
