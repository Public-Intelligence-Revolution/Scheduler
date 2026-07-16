"""Authentication and authorization dependencies for the API."""

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from scheduler.core.config import Settings, get_settings


async def verify_auth_token(
    x_network_auth_token: Annotated[str | None, Header(alias="X-Network-Auth-Token")] = None,
    settings: Annotated[Settings, Depends(get_settings)] = None,  # type: ignore
) -> None:
    """Validate that the incoming request includes the configured security token."""
    if (
        settings is not None
        and settings.network_auth_token is not None
        and x_network_auth_token != settings.network_auth_token
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )
