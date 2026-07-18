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
FALLBACK_PUBLIC_KEY = (
    "-----BEGIN PUBLIC KEY-----\n"
    "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA0Y16Z9B5u1fS6n7kC3h2\n"
    "D5v7B6z9S9fpXG5B6Q6B8c1P8G8L8E1o9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P\n"
    "9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P\n"
    "9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P\n"
    "9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P\n"
    "9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P9P\n"
    "-----END PUBLIC KEY-----"
)


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

    Secured by JWT authentication and rate-limited via a Token Bucket algorithm.

    Args:
        request: FastAPI Request context.
        task: Deserialized client task details.
        payload: Decoded JWT claims dict (via verify_jwt dependency).

    Returns:
        Status object signaling log commitment.
    """
    tenant_id = payload["tenant_id"]

    # 1. Rate-Limiter Guard
    rate_limiter = getattr(request.app.state, "rate_limiter", None)
    if rate_limiter is not None:
        allowed = await rate_limiter.acquire(tenant_id)
        if not allowed:
            logger.warning("ingress_rate_limit_tripped", tenant_id=tenant_id)
            raise HTTPException(
                status_code=429, detail="Rate limit exceeded. Multi-tenant quota exhausted."
            )

    # 2. Consensus Engine Retrieval
    registry = getattr(request.app.state, "registry", None)
    consensus_engine = getattr(registry, "consensus_engine", None)

    if not consensus_engine or not consensus_engine.is_active():
        logger.error("ingress_consensus_engine_offline")
        raise HTTPException(
            status_code=503, detail="Control plane consensus engine is currently offline."
        )

    # 3. Propagate entry to Raft cluster log
    try:
        await consensus_engine.propose(task.action, task.data)
    except Exception as e:
        logger.error("ingress_consensus_proposal_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Consensus log commitment failed: {e}") from e

    return {"status": "committed", "task_id": task.task_id}
