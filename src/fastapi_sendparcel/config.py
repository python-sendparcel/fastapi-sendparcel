"""FastAPI adapter configuration."""

from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SendparcelConfig(BaseSettings):
    """Runtime config for FastAPI adapter.

    Reads from environment variables with SENDPARCEL_ prefix.
    """

    model_config = SettingsConfigDict(env_prefix="SENDPARCEL_")

    default_provider: str
    providers: dict[str, dict[str, Any]] = Field(default_factory=dict)

    # Retry settings
    retry_max_attempts: int = 5
    retry_backoff_seconds: int = 60
    retry_enabled: bool = True
