from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from datetime import UTC, datetime
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
        api_key = self.api_key
        if base_url is None or api_key is None:  # _ready() raises first; narrows for static analysis.
            raise FortyGuardError("fortyguard_not_configured", "FortyGuard is not configured")
        client = self._client or httpx.AsyncClient(base_url=base_url, timeout=self.timeout)
        try:
            for attempt in range(self.max_attempts):
                try:
                    response = await client.request(
                        method,
                        path,
                        headers={"api-key": api_key, "Content-Type": "application/json"},
                        **kwargs,
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
        response = await self._request("POST", "/v1/heatmap", json=self._heatmap_payload(payload))
        data = response.get("data")
        data = data if isinstance(data, dict) else {}
        activity_id = data.get("activity_id") or response.get("activity_id") or response.get("id")
        if not isinstance(activity_id, str) or not activity_id:
            raise FortyGuardError(
                "fortyguard_invalid_response", "FortyGuard response omitted activity identifier"
            )
        return activity_id

    @staticmethod
    def _heatmap_payload(payload: dict[str, object]) -> dict[str, object]:
        """Translate CoolProof's stable request shape to FortyGuard v1.

        CoolProof stores the zone geometry and optional parameters in a provider-
        neutral envelope. FortyGuard requires ``polygon_aoi`` and ``date_time``
        at the top level, so the adapter owns that vendor-specific translation.
        """
        geometry = payload.get("polygon_aoi") or payload.get("geometry")
        if not isinstance(geometry, dict):
            raise FortyGuardError("fortyguard_invalid_request", "A polygon geometry is required")
        if geometry.get("type") == "FeatureCollection":
            polygon_aoi: dict[str, object] = geometry
        else:
            polygon_aoi = {
                "type": "FeatureCollection",
                "features": [{"type": "Feature", "properties": {}, "geometry": geometry}],
            }
        raw_parameters = payload.get("parameters")
        parameters = raw_parameters if isinstance(raw_parameters, dict) else {}
        now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
        date_time = parameters.get("date_time")
        if not isinstance(date_time, dict):
            date_time = {
                "start_date": now.date().isoformat(),
                "start_time": now.strftime("%H:%M"),
                "filter_type": 1,
            }
        analytic_type = parameters.get("analytic_type")
        if not isinstance(analytic_type, str):
            analytic_type = "exceedance" if parameters.get("include_exceedance") else "tcm"
        granularity = parameters.get("granularity", parameters.get("resolution", 100))
        if isinstance(granularity, str) and granularity.endswith("m"):
            granularity = int(granularity[:-1])
        result: dict[str, object] = {
            "polygon_aoi": polygon_aoi,
            "date_time": date_time,
            "granularity": granularity,
            "analytic_type": analytic_type,
        }
        for key in ("threshold", "direction"):
            if key in parameters:
                result[key] = parameters[key]
        return result

    async def get_activity(self, activity_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/v1/status/{activity_id}")
