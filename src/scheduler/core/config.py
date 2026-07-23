"""Application configuration via environment variables."""

import json
from enum import StrEnum
from functools import lru_cache
from typing import Any

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)


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

    # Zenoh WAN Networking
    zenoh_listen_endpoints: list[str] = Field(
        default_factory=lambda: ["tcp/0.0.0.0:7447"],
        validation_alias=AliasChoices(
            "SCHEDULER_ZENOH_LISTEN_ENDPOINTS", "ZENOH_LISTEN_ENDPOINTS"
        ),
        description="Zenoh TCP endpoints to listen on for WAN node connections.",
    )
    zenoh_peer_endpoints: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("SCHEDULER_ZENOH_PEER_ENDPOINTS", "ZENOH_PEER_ENDPOINTS"),
        description="Zenoh WAN endpoints of peer Schedulers.",
    )
    zenoh_multicast_scouting: bool = Field(
        default=True,
        description="Enable/disable local LAN multicast scouting.",
    )

    @field_validator("zenoh_listen_endpoints", "zenoh_peer_endpoints", mode="before")
    @classmethod
    def parse_string_list(cls, v: Any) -> list[str]:
        """Parse list of strings from comma-separated string, JSON, or list."""
        raw_items: list[Any] = []
        if isinstance(v, list):
            raw_items = v
        elif isinstance(v, str):
            val = v.strip()
            if not val:
                return []
            if val.startswith("[") and val.endswith("]"):
                try:
                    parsed = json.loads(val)
                    raw_items = parsed if isinstance(parsed, list) else [val]
                except json.JSONDecodeError:
                    raw_items = [val]
            else:
                raw_items = val.split(",")
        else:
            return []

        parsed_items: list[str] = []
        for item in raw_items:
            item_str = str(item).strip()
            if not item_str:
                raise ValueError("List element cannot be empty or whitespace-only.")
            parsed_items.append(item_str)
        return parsed_items

    @classmethod
    def settings_customise_sources(
        cls,
        _settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Customise settings sources to allow lenient list parsing in env / dotenv."""
        if hasattr(env_settings, "decode_complex_value"):
            orig_env_decode = env_settings.decode_complex_value

            def custom_env_decode(field_name: str, field: Any, value: Any) -> Any:
                if field_name in ("zenoh_listen_endpoints", "zenoh_peer_endpoints"):
                    try:
                        return json.loads(value)
                    except (ValueError, TypeError, json.JSONDecodeError):
                        return value
                return orig_env_decode(field_name, field, value)

            env_settings.decode_complex_value = custom_env_decode  # type: ignore

        if hasattr(dotenv_settings, "decode_complex_value"):
            orig_dotenv_decode = dotenv_settings.decode_complex_value

            def custom_dotenv_decode(field_name: str, field: Any, value: Any) -> Any:
                if field_name in ("zenoh_listen_endpoints", "zenoh_peer_endpoints"):
                    try:
                        return json.loads(value)
                    except (ValueError, TypeError, json.JSONDecodeError):
                        return value
                return orig_dotenv_decode(field_name, field, value)

            dotenv_settings.decode_complex_value = custom_dotenv_decode  # type: ignore

        return (
            init_settings,
            env_settings,
            dotenv_settings,
            file_secret_settings,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings.

    Uses ``lru_cache`` so environment variables are read once at startup.
    Override in tests via ``app.dependency_overrides[get_settings]``.
    """
    return Settings()
