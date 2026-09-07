"""Typed runtime settings loaded exclusively from environment variables."""

from __future__ import annotations

from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ProviderName = Literal["ollama", "openai", "anthropic", "xai"]
ContextSharingLevel = Literal["minimal", "sanitized", "full"]


class LazySettings(BaseSettings):
    """Secret-bearing runtime configuration; never persist this model to disk."""

    model_config = SettingsConfigDict(env_prefix="LAZY_", env_file=".env", extra="ignore")

    ollama_host: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:7b"
    openai_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    xai_api_key: SecretStr | None = None
