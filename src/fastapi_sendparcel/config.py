"""FastAPI adapter configuration."""

from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings


class SendparcelConfig(BaseSettings):
    """Runtime config for FastAPI adapter."""

    default_provider: str
    providers: dict[str, dict[str, Any]] = Field(default_factory=dict)
