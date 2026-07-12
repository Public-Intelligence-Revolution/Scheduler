"""Node registration and discovery endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from scheduler.models.node import Node
from scheduler.registry.node_registry import NodeRegistry

router = APIRouter(tags=["nodes"])


def get_registry(request: Request) -> NodeRegistry:
    """Retrieve the NodeRegistry from application state."""
    registry: NodeRegistry = request.app.state.registry
    return registry


RegistryDep = Annotated[NodeRegistry, Depends(get_registry)]


@router.post("/nodes/register", response_model=Node, status_code=status.HTTP_201_CREATED)
async def register_node(
    node: Node,
    registry: RegistryDep,
) -> Node:
    """Register a compute node with the scheduler."""
    try:
        registry.register(node)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Node already registered: {node.node_id}",
        ) from None
    return node


@router.get("/nodes", response_model=list[Node])
async def list_nodes(
    registry: RegistryDep,
) -> list[Node]:
    """List all registered compute nodes."""
    return registry.list()


@router.get("/nodes/{node_id}", response_model=Node)
async def get_node(
    node_id: str,
    registry: RegistryDep,
) -> Node:
    """Get a specific node by ID."""
    node = registry.get(node_id)
    if node is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node not found: {node_id}",
        )
    return node
