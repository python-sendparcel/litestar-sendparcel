"""Litestar adapter configuration."""

from __future__ import annotations

from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings


class SendparcelConfig(BaseSettings):
    """Runtime config for Litestar adapter."""

    default_provider: str
    providers: dict[str, dict[str, Any]] = Field(default_factory=dict)
