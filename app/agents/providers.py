"""LLM provider boundary for governed agent runs.

Only structured JSON crosses this boundary. Provider failures are surfaced as
safe errors and credentials are never included in exceptions or telemetry.
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
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

    async def generate(self, *, agent: str, context: dict[str, object]) -> AgentOutput: ...

    async def generate_structured(self, *, agent: str, context: dict[str, object]) -> AgentOutput: ...

    def stream(self, *, agent: str, context: dict[str, object]) -> AsyncIterator[str]: ...

    async def tool_call(
        self, *, agent: str, context: dict[str, object], tools: list[dict[str, object]]
    ) -> dict[str, object]: ...


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

    async def generate(self, *, agent: str, context: dict[str, object]) -> AgentOutput:
        return await self.complete(agent=agent, context=context)

    async def generate_structured(self, *, agent: str, context: dict[str, object]) -> AgentOutput:
        return await self.complete(agent=agent, context=context)

    async def tool_call(
        self, *, agent: str, context: dict[str, object], tools: list[dict[str, object]]
    ) -> dict[str, object]:
        # Deterministic mode never invents a tool selection.
        return {"tool": "none", "agent": agent, "available_tools": len(tools), "context_keys": sorted(context)}

    async def _empty_stream(self, *, agent: str, context: dict[str, object]) -> AsyncIterator[str]:
        output = await self.complete(agent=agent, context=context)
        yield output.summary

    def stream(self, *, agent: str, context: dict[str, object]) -> AsyncIterator[str]:
        return self._empty_stream(agent=agent, context=context)


class HTTPJSONProvider:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        name: str,
        endpoint: str = "/v1/agent/completions",
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.name = name
        self.endpoint = endpoint

    def request_payload(self, *, agent: str, context: dict[str, object]) -> dict[str, object]:
        """Build the provider-specific request without retaining raw prompts.

        Backboard's adapter uses its agent endpoint, while NIM is OpenAI
        compatible and uses chat completions.  Keeping the shape at this
        boundary prevents the graph from depending on either provider.
        """
        return {"model": self.model, "agent": agent, "context": context}

    async def complete(self, *, agent: str, context: dict[str, object]) -> AgentOutput:
        # Context intentionally contains sanitized state only. Do not add raw
        # prompts or document text to this request or to logs.
        payload = self.request_payload(agent=agent, context=context)
        try:
            async with httpx.AsyncClient(timeout=45) as client:
                response = await client.post(
                    f"{self.base_url}{self.endpoint}",
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

    async def generate(self, *, agent: str, context: dict[str, object]) -> AgentOutput:
        return await self.complete(agent=agent, context=context)

    async def generate_structured(self, *, agent: str, context: dict[str, object]) -> AgentOutput:
        return await self.complete(agent=agent, context=context)

    async def tool_call(
        self, *, agent: str, context: dict[str, object], tools: list[dict[str, object]]
    ) -> dict[str, object]:
        payload = self.request_payload(agent=agent, context=context)
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
        try:
            async with httpx.AsyncClient(timeout=45) as client:
                response = await client.post(
                    f"{self.base_url}{self.endpoint}",
                    json=payload,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                response.raise_for_status()
                body = response.json()
            if not isinstance(body, dict):
                raise TypeError("provider response is not an object")
            raw: object = body.get("tool_call", body)
            if isinstance(raw, dict) and "choices" in raw:
                choices = raw.get("choices")
                if isinstance(choices, list) and choices:
                    message = choices[0].get("message", {})
                    if isinstance(message, dict):
                        calls = message.get("tool_calls", [])
                        raw = calls[0] if isinstance(calls, list) and calls else message
            if not isinstance(raw, dict):
                raise TypeError("provider tool response is not an object")
            return {str(key): value for key, value in raw.items()}
        except (httpx.HTTPError, ValueError, TypeError, KeyError, IndexError) as exc:
            raise ProviderError(f"{self.name}_tool_call_failed") from exc

    async def _stream(self, *, agent: str, context: dict[str, object]) -> AsyncIterator[str]:
        payload = self.request_payload(agent=agent, context=context)
        payload["stream"] = True
        try:
            async with httpx.AsyncClient(timeout=45) as client, client.stream(
                "POST", f"{self.base_url}{self.endpoint}", json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        body = json.loads(data)
                    except (TypeError, ValueError):
                        continue
                    if isinstance(body, dict):
                        text = body.get("text")
                        if not isinstance(text, str):
                            choices = body.get("choices")
                            if isinstance(choices, list) and choices:
                                delta = choices[0].get("delta", {})
                                text = delta.get("content") if isinstance(delta, dict) else None
                        if isinstance(text, str) and text:
                            yield text
        except (httpx.HTTPError, ValueError, TypeError, KeyError, IndexError) as exc:
            raise ProviderError(f"{self.name}_stream_failed") from exc

    def stream(self, *, agent: str, context: dict[str, object]) -> AsyncIterator[str]:
        return self._stream(agent=agent, context=context)


class NIMProvider(HTTPJSONProvider):
    def __init__(self, settings: Settings):
        if not settings.nim_base_url or not settings.nim_api_key:
            raise ProviderError("nim_provider_not_configured")
        super().__init__(
            base_url=settings.nim_base_url,
            api_key=settings.nim_api_key.get_secret_value(),
            model=settings.nim_model,
            name="nim",
            endpoint="/v1/chat/completions",
        )

    def request_payload(self, *, agent: str, context: dict[str, object]) -> dict[str, object]:
        # NIM accepts the OpenAI chat-completions contract.  The system
        # instruction requires a schema-valid JSON object so AgentOutput can
        # reject malformed or hallucinated responses at the boundary.
        return {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        f"You are the CoolProof {agent} agent. Return only a JSON object "
                        "with keys summary, citations, facts, confidence, needs_approval."
                    ),
                },
                {"role": "user", "content": json.dumps(context, sort_keys=True)},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }


class BackboardProvider(HTTPJSONProvider):
    def __init__(self, settings: Settings):
        if not settings.backboard_base_url or not settings.backboard_api_key:
            raise ProviderError("backboard_provider_not_configured")
        super().__init__(
            base_url=settings.backboard_base_url,
            api_key=settings.backboard_api_key.get_secret_value(),
            model=settings.backboard_model,
            name="backboard",
            endpoint=settings.backboard_completion_endpoint,
        )


# Descriptive name used by deployment documentation; retain the short class
# name for compatibility with existing imports.
NvidiaNimProvider = NIMProvider


def provider_from_settings(settings: Settings) -> LLMProvider:
    if settings.agent_provider in {"nim", "nvidia_nim"}:
        return NIMProvider(settings)
    if settings.agent_provider == "backboard":
        return BackboardProvider(settings)
    return DeterministicProvider()
