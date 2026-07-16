"""Application configuration via environment variables."""

from enum import StrEnum
from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    """Deployment environment."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    All settings can be overridden via environment variables prefixed
    with ``SCHEDULER_``. For example: ``SCHEDULER_LOG_LEVEL=debug``.
    """

    model_config = SettingsConfigDict(
        env_prefix="SCHEDULER_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        populate_by_name=True,
    )

    environment: Environment = Environment.DEVELOPMENT
    debug: bool = False
    log_level: str = "info"
    host: str = "0.0.0.0"
    port: int = 8000
    network_auth_token: str | None = Field(
        default=None,
        validation_alias=AliasChoices("SCHEDULER_NETWORK_AUTH_TOKEN", "NETWORK_AUTH_TOKEN"),
        description="Secure network authentication token.",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings.

    Uses ``lru_cache`` so environment variables are read once at startup.
    Override in tests via ``app.dependency_overrides[get_settings]``.
    """
    return Settings()
