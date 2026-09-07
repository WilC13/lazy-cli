"""Second-line LLM semantic command-risk assessment."""

from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel, Field

from lazy_cli.config import UserConfig
from lazy_cli.core.generator import CloudContextConsentRequired, GenerationError
from lazy_cli.core.guardrail import RiskLevel
from lazy_cli.settings import LazySettings


class SemanticRiskAssessment(BaseModel):
    """Model-produced risk decision used in addition to deterministic L1 checks."""

    level: RiskLevel
    reason: str = Field(min_length=1)


class SemanticRiskAssessor:
    """Ask the selected model to evaluate intent and impact of one command."""

    def __init__(self, settings: LazySettings, config: UserConfig, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.settings = settings
        self.config = config
        self.transport = transport

    async def assess(self, command: str) -> SemanticRiskAssessment:
        """Return a typed L2 assessment; callers must fail closed on errors."""
        if self.config.provider != "ollama" and not self.config.cloud_context_consent:
            raise CloudContextConsentRequired("Cloud risk assessment requires explicit cloud context consent.")
        system = (
            "Assess the safety impact of this shell command. Return only JSON with "
            "level (safe, warning, or critical) and reason. Critical means irreversible "
            "or destructive; warning means privileged, externally visible, or data-changing."
        )
        content = await self._complete(system, command)
        try:
            return SemanticRiskAssessment.model_validate_json(content)
        except ValueError as error:
            raise GenerationError("Risk assessor returned invalid JSON.") from error

    async def _complete(self, system: str, command: str) -> str:
        provider = self.config.provider
        model = self.config.model or _default_model(provider, self.settings)
        async with httpx.AsyncClient(transport=self.transport) as client:
            if provider == "ollama":
                response = await client.post(
                    f"{self.settings.ollama_host.rstrip('/')}/api/chat",
                    json={"model": model, "stream": False, "format": SemanticRiskAssessment.model_json_schema(), "messages": [{"role": "system", "content": system}, {"role": "user", "content": command}]},
                    timeout=30.0,
                )
                _raise(response)
                content = response.json().get("message", {}).get("content")
            elif provider in {"openai", "xai"}:
                endpoint = "https://api.openai.com/v1/chat/completions" if provider == "openai" else "https://api.x.ai/v1/chat/completions"
                key = self.settings.openai_api_key if provider == "openai" else self.settings.xai_api_key
                response = await client.post(endpoint, headers={"Authorization": f"Bearer {_key(key, provider)}"}, json={"model": model, "response_format": {"type": "json_object"}, "messages": [{"role": "system", "content": system}, {"role": "user", "content": command}]}, timeout=30.0)
                _raise(response)
                content = response.json().get("choices", [{}])[0].get("message", {}).get("content")
            else:
                response = await client.post("https://api.anthropic.com/v1/messages", headers={"x-api-key": _key(self.settings.anthropic_api_key, provider), "anthropic-version": "2023-06-01"}, json={"model": model, "max_tokens": 256, "system": system, "messages": [{"role": "user", "content": command}]}, timeout=30.0)
                _raise(response)
                blocks = response.json().get("content", [])
                content = blocks[0].get("text") if blocks and isinstance(blocks[0], dict) else None
        if not isinstance(content, str):
            raise GenerationError("Risk assessor response did not contain text content.")
        return content


def _default_model(provider: str, settings: LazySettings) -> str:
    return {"ollama": settings.ollama_model, "openai": "gpt-4o-mini", "anthropic": "claude-sonnet-4-5", "xai": "grok-4"}[provider]


def _key(value: Any, provider: str) -> str:
    if value is None or not value.get_secret_value():
        raise GenerationError(f"Missing API key for {provider} risk assessment.")
    return value.get_secret_value()


def _raise(response: httpx.Response) -> None:
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as error:
        raise GenerationError(f"Risk assessment request failed: {error.response.status_code}") from error
