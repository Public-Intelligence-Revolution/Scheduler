"""Ingress gateway API endpoint for client task submissions."""

import os
from typing import Annotated, Any

import jwt
import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

logger = structlog.stdlib.get_logger()

router = APIRouter(prefix="/api/v1/tasks")

# Standard dummy RSA public key PEM as fallback
FALLBACK_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAuPdw3Iiuj6UrD6hMY1uZ
SNXPOBfJ4wra50siLS0+DYThpmcQkhzeqvnWh4zLeiBlu4Tk563XZYozkXaaL1bY
/a6MYPC1A5E5H4RalM7ZH0HUNBWgM+8WEZ7utSA5GRO59K9zeP7Jj+zKCDEXFdwa
pRD330+s1UfXfK+wJCtNqCuRQBQ5CmBAbNP2p6pYxOcTCYNHhgVayDuR8kJVi04m
n3ujts5RifLbwGn+Py/9IFYbLl2RW/cN3dNWm/eH/1Q0C7MJkZv8br4KEwevadVi
ms0tJViEjM0cHJaH5iN7e9qxGaw1Cq/sM2M27TyZfRZMGLeH8GKRDsg3pY0nV8zu
NQIDAQAB
-----END PUBLIC KEY-----"""


class TaskSubmission(BaseModel):
    """Pydantic model representing the task structure for client submission."""

    task_id: str = Field(..., description="Unique identifier for the task.")
    action: str = Field(..., description="State machine action/instruction payload.")
    data: dict[str, Any] = Field(
        default_factory=dict, description="Arbitrary task execution arguments."
    )


def verify_jwt(request: Request, authorization: str = Header(...)) -> dict[str, Any]:
    """Dependency injection validator to check asymmetric JWT signature.

    Args:
        request: FastAPI Request instance to pull app state configuration.
        authorization: HTTP Authorization header containing Bearer token.

    Returns:
        The decoded JWT payload claims.

    Raises:
        HTTPException (401) on validation error.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401, detail="Invalid Authorization header format. Must be Bearer <JWT>."
        )

    token = authorization.split(" ")[1]
    public_key = getattr(request.app.state, "jwt_public_key", None)
    if not public_key:
        public_key = os.environ.get("JWT_PUBLIC_KEY", FALLBACK_PUBLIC_KEY)

    try:
        # Asymmetric signature verification using RS256
        payload = jwt.decode(token, public_key, algorithms=["RS256"])
    except jwt.PyJWTError as e:
        logger.warning("ingress_jwt_verification_failed", error=str(e))
        raise HTTPException(
            status_code=401, detail=f"JWT signature verification failed: {e}"
        ) from e

    if "tenant_id" not in payload:
        raise HTTPException(
            status_code=401, detail="Invalid claims: Missing 'tenant_id' in token payload."
        )

    return payload


@router.post("/submit")
async def submit_task(
    request: Request,
    task: TaskSubmission,
    payload: Annotated[dict[str, Any], Depends(verify_jwt)],
) -> dict[str, str]:
    """Dedicated ingress endpoint to submit tasks to the consensus log.

    Secured by JWT authentication, rate-limited, scheduled using two-stage Strategy,
    and committed to consensus log.

    Args:
        request: FastAPI Request context.
        task: Deserialized client task details.
        payload: Decoded JWT claims dict (via verify_jwt dependency).

    Returns:
        Status object signaling scheduled task tracking info.
    """
    tenant_id = payload["tenant_id"]

    # 1. Rate-Limiter Guard
    rate_limiter = getattr(request.app.state, "rate_limiter", None)
    if rate_limiter is not None:
        allowed = await rate_limiter.acquire(tenant_id)
        if not allowed:
            logger.warning("ingress_rate_limit_tripped", tenant_id=tenant_id)
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Multi-tenant quota exhausted.",
            )

    # 2. Scheduling Engine Retrieval & Execution
    scheduling_engine = getattr(request.app.state, "scheduling_engine", None)
    if scheduling_engine is None:
        logger.error("ingress_scheduling_engine_uninitialized")
        raise HTTPException(
            status_code=500, detail="Scheduling engine is uninitialized."
        )

    task_data = {
        "task_id": task.task_id,
        "requirements": {
            "model_name": task.data.get("model_name") or task.data.get("model"),
            "min_vram_gb": task.data.get("min_vram_gb") or task.data.get("vram"),
            "backend_type": task.data.get("backend_type"),
        },
    }

    try:
        tx_hash, node_id = await scheduling_engine.schedule_task(task_data)
    except ValueError as e:
        logger.warning("ingress_scheduling_failed", error=str(e))
        raise HTTPException(status_code=400, detail=str(e)) from e

    # 3. Consensus Engine Log Commitment
    registry = getattr(request.app.state, "registry", None)
    consensus_engine = getattr(registry, "consensus_engine", None)

    if consensus_engine is not None and consensus_engine.is_active():
        try:
            await consensus_engine.propose(
                "allocate_task",
                {
                    "task_id": task.task_id,
                    "node_id": node_id,
                    "tx_hash": tx_hash,
                    "action": task.action,
                    "data": task.data,
                },
            )
        except Exception as e:
            logger.error("ingress_consensus_proposal_failed", error=str(e))
            raise HTTPException(
                status_code=500,
                detail=f"Consensus log commitment failed: {e}",
            ) from e

    return {
        "status": "scheduled",
        "task_id": task.task_id,
        "node_id": node_id,
        "tx_hash": tx_hash,
    }
