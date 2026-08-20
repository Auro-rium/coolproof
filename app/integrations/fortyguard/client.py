from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class FortyGuardError(Exception):
    code: str
    message: str
    retryable: bool = False


class FortyGuardClient:
    """Small async adapter for the provider activity API.

    The concrete paths deliberately live here so the rest of the system only sees
    validated activities and normalized results.
    """

    def __init__(
        self,
        base_url: str | None,
        api_key: str | None,
        *,
        timeout: float = 30,
        max_attempts: int = 5,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url, self.api_key, self.timeout, self.max_attempts = (
            base_url,
            api_key,
            timeout,
            max_attempts,
        )
        self._client = client
        self._failures = 0
        self._open_until = 0.0

    def _ready(self) -> None:
        if not self.base_url or not self.api_key:
            raise FortyGuardError("fortyguard_not_configured", "FortyGuard is not configured")
        if self._open_until > asyncio.get_running_loop().time():
            raise FortyGuardError(
                "fortyguard_circuit_open", "FortyGuard is temporarily unavailable", True
            )

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        self._ready()
        own_client = self._client is None
        base_url = self.base_url
        if base_url is None:  # _ready() raises first; narrows for static analysis.
            raise FortyGuardError("fortyguard_not_configured", "FortyGuard is not configured")
        client = self._client or httpx.AsyncClient(base_url=base_url, timeout=self.timeout)
        try:
            for attempt in range(self.max_attempts):
                try:
                    response = await client.request(
                        method, path, headers={"Authorization": f"Bearer {self.api_key}"}, **kwargs
                    )
                    if response.status_code == 429 or response.status_code >= 500:
                        raise FortyGuardError(
                            "fortyguard_rate_limited"
                            if response.status_code == 429
                            else "fortyguard_unavailable",
                            "FortyGuard temporarily failed",
                            True,
                        )
                    if response.status_code >= 400:
                        raise FortyGuardError(
                            "fortyguard_request_rejected", "FortyGuard rejected the request"
                        )
                    payload = response.json()
                    if not isinstance(payload, dict):
                        raise FortyGuardError(
                            "fortyguard_invalid_response", "FortyGuard returned an invalid response"
                        )
                    self._failures = 0
                    return payload
                except (httpx.HTTPError, FortyGuardError) as exc:
                    retryable = isinstance(exc, httpx.HTTPError) or (
                        isinstance(exc, FortyGuardError) and exc.retryable
                    )
                    if not retryable or attempt + 1 >= self.max_attempts:
                        self._failures += 1
                        if self._failures >= 3:
                            self._open_until = asyncio.get_running_loop().time() + 30
                        if isinstance(exc, FortyGuardError):
                            raise
                        raise FortyGuardError(
                            "fortyguard_unavailable", "FortyGuard is unavailable", True
                        ) from exc
                    await asyncio.sleep(min(8.0, 0.5 * 2**attempt) + random.uniform(0, 0.25))
        finally:
            if own_client:
                await client.aclose()
        raise AssertionError("unreachable")

    async def create_analysis(self, payload: dict[str, object]) -> str:
        response = await self._request("POST", "/activities", json=payload)
        activity_id = response.get("activity_id") or response.get("id")
        if not isinstance(activity_id, str) or not activity_id:
            raise FortyGuardError(
                "fortyguard_invalid_response", "FortyGuard response omitted activity identifier"
            )
        return activity_id

    async def get_activity(self, activity_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/activities/{activity_id}")
