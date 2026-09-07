"""Non-secret, user-selectable lazy-cli preferences."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from lazy_cli.settings import ContextSharingLevel, ProviderName

_CONFIG_PATH = Path.home() / ".config" / "lazy-cli" / "config.json"


class UserConfig(BaseModel):
    """Preferences safe to write to disk; credentials are deliberately absent."""

    provider: ProviderName = "ollama"
    model: str | None = None
    context_sharing: ContextSharingLevel = "sanitized"
    cloud_context_consent: bool = False


def load_config(path: Path = _CONFIG_PATH) -> UserConfig:
    """Load valid user preferences, or return secure defaults."""
    try:
        return UserConfig.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return UserConfig()


def save_config(config: UserConfig, path: Path = _CONFIG_PATH) -> None:
    """Persist non-secret preferences with owner-only file permissions."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(json.dumps(config.model_dump(), indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)
