"""Scheduler selection API endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from scheduler.api.auth import verify_auth_token
from scheduler.api.nodes import get_registry
from scheduler.registry.node_registry import NodeRegistry
from scheduler.scheduler.algorithm import Scheduler

router = APIRouter(tags=["schedule"])


class ScheduleRequest(BaseModel):
    """Inference request asking for a specific model."""

    model_name: str = Field(description="The name of the requested AI model")


class ScheduleResponse(BaseModel):
    """Response returning the selected compute node."""

    node_id: str = Field(description="Unique identifier of the selected node")
    hostname: str = Field(description="Hostname of the selected node")
    ip_address: str = Field(description="IP address of the selected node")
    region: str = Field(description="Geographic region of the selected node")


def get_scheduler(
    registry: Annotated[NodeRegistry, Depends(get_registry)],
) -> Scheduler:
    """Dependency provider for the Scheduler instance."""
    return Scheduler(registry)


SchedulerDep = Annotated[Scheduler, Depends(get_scheduler)]


@router.post(
    "/schedule",
    response_model=ScheduleResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(verify_auth_token)],
)
async def schedule_request(
    request: ScheduleRequest,
    scheduler: SchedulerDep,
) -> ScheduleResponse:
    """Select the best compute node to run the requested model."""
    try:
        node = await scheduler.select_node(request.model_name)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from None

    return ScheduleResponse(
        node_id=node.node_id,
        hostname=node.hostname,
        ip_address=node.ip_address,
        region=node.region,
    )
