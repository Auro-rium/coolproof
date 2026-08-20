"""LLM provider boundary for governed agent runs.

Only structured JSON crosses this boundary. Provider failures are surfaced as
safe errors and credentials are never included in exceptions or telemetry.
"""
from __future__ import annotations

import json
from typing import Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.config import Settings


class ProviderError(RuntimeError):
    """A safe, provider-independent failure."""


class AgentOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str = Field(min_length=1, max_length=4000)
    citations: list[str] = Field(default_factory=list, max_length=50)
    facts: dict[str, object] = Field(default_factory=dict)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    needs_approval: bool = False


class LLMProvider(Protocol):
    name: str

    async def complete(self, *, agent: str, context: dict[str, object]) -> AgentOutput: ...


class DeterministicProvider:
    name = "deterministic"

    async def complete(self, *, agent: str, context: dict[str, object]) -> AgentOutput:
        # The deterministic default is safe for local/offline operation and
        # keeps calculations in domain services rather than in an LLM.
        return AgentOutput(
            summary=f"{agent} completed using deterministic domain services",
            facts={"agent": agent, "input_keys": sorted(context)},
            confidence=1.0,
        )


class HTTPJSONProvider:
    def __init__(self, *, base_url: str, api_key: str, model: str, name: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.name = name

    async def complete(self, *, agent: str, context: dict[str, object]) -> AgentOutput:
        # Context intentionally contains sanitized state only. Do not add raw
        # prompts or document text to this request or to logs.
        payload = {"model": self.model, "agent": agent, "context": context}
        try:
            async with httpx.AsyncClient(timeout=45) as client:
                response = await client.post(
                    f"{self.base_url}/v1/agent/completions",
                    json=payload,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                response.raise_for_status()
                body = response.json()
            raw = body.get("output", body)
            # NVIDIA-compatible chat endpoints commonly wrap JSON in
            # choices[0].message.content; Backboard uses output directly.
            if isinstance(raw, dict) and "choices" in raw:
                choices = raw.get("choices")
                if isinstance(choices, list) and choices:
                    message = choices[0].get("message", {})
                    raw = message.get("content", raw) if isinstance(message, dict) else raw
            if isinstance(raw, str):
                raw = json.loads(raw)
            return AgentOutput.model_validate(raw)
        except (httpx.HTTPError, ValueError, TypeError, ValidationError, KeyError) as exc:
            raise ProviderError(f"{self.name}_provider_failed") from exc


class NIMProvider(HTTPJSONProvider):
    def __init__(self, settings: Settings):
        if not settings.nim_base_url or not settings.nim_api_key:
            raise ProviderError("nim_provider_not_configured")
        super().__init__(
            base_url=settings.nim_base_url,
            api_key=settings.nim_api_key.get_secret_value(),
            model=settings.nim_model,
            name="nim",
        )


class BackboardProvider(HTTPJSONProvider):
    def __init__(self, settings: Settings):
        if not settings.backboard_base_url or not settings.backboard_api_key:
            raise ProviderError("backboard_provider_not_configured")
        super().__init__(
            base_url=settings.backboard_base_url,
            api_key=settings.backboard_api_key.get_secret_value(),
            model=settings.backboard_model,
            name="backboard",
        )


def provider_from_settings(settings: Settings) -> LLMProvider:
    if settings.agent_provider == "nim":
        return NIMProvider(settings)
    if settings.agent_provider == "backboard":
        return BackboardProvider(settings)
    return DeterministicProvider()
