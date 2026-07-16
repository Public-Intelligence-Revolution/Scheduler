"""Heartbeat receiver endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from scheduler.api.auth import verify_auth_token
from scheduler.api.nodes import get_registry
from scheduler.models.heartbeat import Heartbeat
from scheduler.registry.node_registry import NodeRegistry

router = APIRouter(tags=["heartbeat"])

RegistryDep = Annotated[NodeRegistry, Depends(get_registry)]


@router.post(
    "/heartbeat",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(verify_auth_token)],
)
async def receive_heartbeat(
    heartbeat: Heartbeat,
    registry: RegistryDep,
) -> dict[str, str]:
    """Receive a heartbeat update from a compute node."""
    try:
        await registry.update_heartbeat(heartbeat)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node not found: {heartbeat.node_id}",
        ) from None
    return {"status": "ok"}
