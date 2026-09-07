"""Provider-neutral, privacy-gated LLM command generation."""

from __future__ import annotations

import json
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, Field

from lazy_cli.config import UserConfig
from lazy_cli.core.inspector import LocalContext
from lazy_cli.settings import LazySettings, ProviderName


class CommandProposal(BaseModel):
    """The only structured result generators may return."""

    command: str = Field(min_length=1)
    explanation: str = Field(min_length=1)
    assumptions: list[str] = Field(default_factory=list)


class GenerationError(RuntimeError):
    """Raised when a provider cannot safely return a command proposal."""


class CloudContextConsentRequired(GenerationError):
    """Raised before any cloud request is sent without explicit consent."""


class CommandGenerator(Protocol):
    async def generate(self, request: str, context: LocalContext) -> CommandProposal:
        """Generate a structured command proposal."""
        ...


class BaseGenerator:
    """Shared privacy policy and JSON parsing for concrete providers."""

    provider: ProviderName

    def __init__(self, model: str, config: UserConfig) -> None:
        self.model = model
        self.config = config

    def _messages(self, request: str, context: LocalContext) -> tuple[str, str]:
        if self.provider != "ollama" and not self.config.cloud_context_consent:
            raise CloudContextConsentRequired(
                "Cloud context sharing requires explicit consent. Run "
                "'lazy config consent-cloud --yes' first."
            )
        return (
            (
                "You translate natural-language requests into one safe shell command. "
                "Return JSON matching the requested schema. Do not include secrets."
            ),
            f"Request: {request}\n\nLocal context:\n{_context_json(context, self.config.context_sharing)}",
        )

    @staticmethod
    def _proposal(content: str) -> CommandProposal:
        try:
            return CommandProposal.model_validate_json(content)
        except ValueError as error:
            raise GenerationError("Provider returned invalid command JSON.") from error


class OllamaGenerator(BaseGenerator):
    provider: ProviderName = "ollama"

    def __init__(self, model: str, host: str, config: UserConfig, transport: httpx.AsyncBaseTransport | None = None) -> None:
        super().__init__(model, config)
        self.host = host.rstrip("/")
        self.transport = transport

    async def generate(self, request: str, context: LocalContext) -> CommandProposal:
        system, user = self._messages(request, context)
        payload = {
            "model": self.model,
            "stream": False,
            "format": CommandProposal.model_json_schema(),
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        async with httpx.AsyncClient(transport=self.transport) as client:
            response = await client.post(f"{self.host}/api/chat", json=payload, timeout=60.0)
        _raise_for_status(response)
        content = response.json().get("message", {}).get("content")
        if not isinstance(content, str):
            raise GenerationError("Ollama response did not contain message content.")
        return self._proposal(content)


class OpenAICompatibleGenerator(BaseGenerator):
    """Adapter for OpenAI-compatible chat-completions APIs, including xAI."""

    def __init__(self, provider: ProviderName, model: str, endpoint: str, api_key: str, config: UserConfig, transport: httpx.AsyncBaseTransport | None = None) -> None:
        super().__init__(model, config)
        self.provider = provider
        self.endpoint = endpoint
        self.api_key = api_key
        self.transport = transport

    async def generate(self, request: str, context: LocalContext) -> CommandProposal:
        system, user = self._messages(request, context)
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_object"},
        }
        async with httpx.AsyncClient(transport=self.transport) as client:
            response = await client.post(
                self.endpoint,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
                timeout=60.0,
            )
        _raise_for_status(response)
        content = response.json().get("choices", [{}])[0].get("message", {}).get("content")
        if not isinstance(content, str):
            raise GenerationError(f"{self.provider} response did not contain message content.")
        return self._proposal(content)


class AnthropicGenerator(BaseGenerator):
    provider: ProviderName = "anthropic"

    def __init__(self, model: str, api_key: str, config: UserConfig, transport: httpx.AsyncBaseTransport | None = None) -> None:
        super().__init__(model, config)
        self.api_key = api_key
        self.transport = transport

    async def generate(self, request: str, context: LocalContext) -> CommandProposal:
        system, user = self._messages(request, context)
        payload = {"model": self.model, "max_tokens": 1024, "system": system, "messages": [{"role": "user", "content": user}]}
        async with httpx.AsyncClient(transport=self.transport) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
                json=payload,
                timeout=60.0,
            )
        _raise_for_status(response)
        blocks = response.json().get("content", [])
        content = blocks[0].get("text") if blocks and isinstance(blocks[0], dict) else None
        if not isinstance(content, str):
            raise GenerationError("Anthropic response did not contain text content.")
        return self._proposal(content)


def create_generator(settings: LazySettings, config: UserConfig, transport: httpx.AsyncBaseTransport | None = None) -> CommandGenerator:
    """Create the selected provider without serializing or storing credentials."""
    model = config.model or _default_model(config.provider, settings)
    if config.provider == "ollama":
        return OllamaGenerator(model, settings.ollama_host, config, transport)
    if config.provider == "openai":
        return OpenAICompatibleGenerator("openai", model, "https://api.openai.com/v1/chat/completions", _secret(settings.openai_api_key, "LAZY_OPENAI_API_KEY"), config, transport)
    if config.provider == "xai":
        return OpenAICompatibleGenerator("xai", model, "https://api.x.ai/v1/chat/completions", _secret(settings.xai_api_key, "LAZY_XAI_API_KEY"), config, transport)
    return AnthropicGenerator(model, _secret(settings.anthropic_api_key, "LAZY_ANTHROPIC_API_KEY"), config, transport)


def _context_json(context: LocalContext, level: str) -> str:
    payload: dict[str, Any] = context.model_dump()
    if level == "minimal":
        payload.pop("environment_variables", None)
        payload.pop("cli_arguments", None)
    # All levels preserve the inspector's invariant: environment values never exist in this model.
    return json.dumps(payload, sort_keys=True)


def _default_model(provider: ProviderName, settings: LazySettings) -> str:
    return {"ollama": settings.ollama_model, "openai": "gpt-4o-mini", "anthropic": "claude-sonnet-4-5", "xai": "grok-4"}[provider]


def _secret(value: Any, variable_name: str) -> str:
    if value is None or not value.get_secret_value():
        raise GenerationError(f"{variable_name} must be set for this provider.")
    return value.get_secret_value()


def _raise_for_status(response: httpx.Response) -> None:
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as error:
        raise GenerationError(f"Provider request failed: {error.response.status_code}") from error
