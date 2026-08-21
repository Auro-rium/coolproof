from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from math import isfinite
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FortyGuardActivity, HeatAnalysis, HeatAnalysisStatus, ProviderCircuit
from app.integrations.fortyguard import FortyGuardClient, FortyGuardError
from app.services.audit import record_audit_event


@dataclass(frozen=True)
class HeatWeights:
    """Versioned, auditable weights for the deterministic exposure score."""
    mean_temperature: float = 0.35
    persistence_hours: float = 0.25
    threshold_exceedance: float = 0.25
    population: float = 0.10
    criticality: float = 0.05
    version: str = "heat-score-v1"

    def __post_init__(self) -> None:
        values = (self.mean_temperature, self.persistence_hours,
                  self.threshold_exceedance, self.population, self.criticality)
        if any(not isfinite(v) or v < 0 for v in values) or sum(values) <= 0:
            raise ValueError("heat weights must be finite and non-negative")

    def normalized(self) -> dict[str, float]:
        values = asdict(self)
        total = sum(values[k] for k in ("mean_temperature", "persistence_hours",
                                        "threshold_exceedance", "population", "criticality"))
        return {k: values[k] / total for k in values if k != "version"}


def calculate_heat_exposure(
    observations: list[dict[str, object]], *, threshold_c: float = 35.0,
    population: float = 0.0, criticality: float = 0.0,
    weights: HeatWeights | None = None,
) -> dict[str, object]:
    """Calculate a reproducible exposure score from provider observations.

    Observations contain ``temperature_c`` and optionally ``hours`` (default 1).
    No model or agent participates in this calculation; all intermediate values
    and the weighting configuration are returned for review and replay.
    """
    if not observations:
        raise ValueError("at least one heat observation is required")
    weights = weights or HeatWeights()
    temps: list[float] = []
    hours: list[float] = []
    for item in observations:
        temp = float(item.get("temperature_c", item.get("temperature", 0)))  # type: ignore[arg-type]
        duration = float(item.get("hours", 1))  # type: ignore[arg-type]
        if not isfinite(temp) or not isfinite(duration) or duration <= 0:
            raise ValueError("observation temperature and hours must be finite; hours > 0")
        temps.append(temp); hours.append(duration)
    total_hours = sum(hours)
    mean_temperature = sum(t * h for t, h in zip(temps, hours)) / total_hours
    exceedance = sum(max(0.0, t - threshold_c) * h for t, h in zip(temps, hours)) / total_hours
    persistence = sum(h for t, h in zip(temps, hours) if t >= threshold_c)
    # Normalize physical dimensions into stable [0,1] components.
    temp_component = max(0.0, min(1.0, (mean_temperature - threshold_c) / 15.0))
    persistence_component = min(1.0, persistence / 24.0)
    exceedance_component = max(0.0, min(1.0, exceedance / 15.0))
    population_component = max(0.0, min(1.0, float(population) / 10000.0))
    criticality_component = max(0.0, min(1.0, float(criticality)))
    w = weights.normalized()
    score = (temp_component*w["mean_temperature"] + persistence_component*w["persistence_hours"] +
             exceedance_component*w["threshold_exceedance"] + population_component*w["population"] +
             criticality_component*w["criticality"])
    return {"method": "deterministic_heat_exposure_v1", "mean_temperature_c": mean_temperature,
            "threshold_c": threshold_c, "persistence_hours": persistence,
            "exposure_hours": persistence, "threshold_exceedance_c": exceedance,
            "exposure_score": round(score, 6), "population": population, "criticality": criticality,
            "weights": {**w, "version": weights.version},
            "provenance": {"observation_count": len(observations), "inputs": "FortyGuard observations"}}


def analysis_idempotency_key(zone_id: UUID, request: dict[str, object]) -> str:
    """Return the provider-credit idempotency key for a heat request.

    FortyGuard charges per analysis, so the key intentionally represents the
    provider query rather than an internal database identifier.  ``zone_id`` is
    retained in the signature for source compatibility; the canonical polygon
    is the geographic scope and is what must participate in the key.
    ``parameters`` is accepted because the public API keeps optional provider
    arguments in that object, while direct integrations may provide the fields
    at the top level.
    """
    del zone_id
    parameters = request.get("parameters")
    params = parameters if isinstance(parameters, dict) else {}

    def value(*names: str) -> object:
        for name in names:
            if name in request:
                return request[name]
            if name in params:
                return params[name]
        return None

    canonical = {
        "polygon": value("polygon", "geometry"),
        "datetime": value("datetime", "date", "timestamp", "time"),
        "analytic_type": value("analytic_type", "analytic", "analysis_type"),
        "threshold": value("threshold", "threshold_c"),
        "granularity": value("granularity", "resolution", "resolution_m"),
    }
    canonical_json = json.dumps(
        canonical, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(canonical_json.encode()).hexdigest()


def normalize_activity(
    payload: dict[str, Any],
) -> tuple[HeatAnalysisStatus, dict[str, object] | None]:
    envelope = payload.get("data")
    data = envelope if isinstance(envelope, dict) else payload
    state = str(data.get("status", payload.get("status", ""))).lower()
    if state in {"queued", "pending"}:
        return HeatAnalysisStatus.QUEUED, None
    if state in {"running", "processing"}:
        return HeatAnalysisStatus.RUNNING, None
    if state in {"succeeded", "completed", "complete"}:
        result = data.get("result") or payload.get("result")
        if not isinstance(result, dict):
            raise FortyGuardError(
                "fortyguard_invalid_response", "Completed activity omitted result data"
            )
        return HeatAnalysisStatus.SUCCEEDED, result
    if state in {"failed", "error", "cancelled"}:
        return HeatAnalysisStatus.FAILED, None
    raise FortyGuardError(
        "fortyguard_invalid_response", "FortyGuard returned an unknown activity status"
    )


class HeatService:
    def __init__(
        self, session: AsyncSession, client: FortyGuardClient, cache_ttl_seconds: int = 86400
    ) -> None:
        self.session, self.client, self.cache_ttl_seconds = session, client, cache_ttl_seconds

    async def submit(
        self, *, organization_id: UUID, project_id: UUID, zone_id: UUID, payload: dict[str, object]
    ) -> tuple[HeatAnalysis, bool]:
        key = analysis_idempotency_key(zone_id, payload)
        existing = await self.session.scalar(
            select(HeatAnalysis)
            .where(
                HeatAnalysis.organization_id == organization_id, HeatAnalysis.idempotency_key == key
            )
            .order_by(HeatAnalysis.created_at.desc())
        )
        now = datetime.now(UTC)
        if existing and (existing.expires_at is None or existing.expires_at > now):
            return existing, True
        # An expired successful result remains a usable stale fallback. Reuse
        # the row and its activity record instead of inserting the same unique
        # idempotency key a second time.
        analysis = existing or HeatAnalysis(
            organization_id=organization_id,
            project_id=project_id,
            zone_id=zone_id,
            idempotency_key=key,
            request_payload=payload,
        )
        if existing is None:
            self.session.add(analysis)
            await self.session.flush()
        try:
            activity_id = await self.client.create_analysis(payload)
        except FortyGuardError as exc:
            if existing is not None and existing.result is not None:
                # Never invent fresh measurements when the upstream is down.
                # Return the last known result and let the API mark it stale.
                analysis.error_code, analysis.error_message = exc.code, exc.message
                await self.session.commit()
                await self.session.refresh(analysis)
                return analysis, True
            analysis.status, analysis.error_code, analysis.error_message = (
                HeatAnalysisStatus.FAILED, exc.code, exc.message
            )
            await self.session.commit()
            raise
        analysis.project_id, analysis.zone_id = project_id, zone_id
        analysis.request_payload = payload
        analysis.status = HeatAnalysisStatus.QUEUED
        analysis.error_code = analysis.error_message = None
        analysis.provider_activity_id = activity_id
        activity = await self.session.scalar(
            select(FortyGuardActivity).where(FortyGuardActivity.analysis_id == analysis.id)
        )
        if activity is None:
            activity = FortyGuardActivity(analysis_id=analysis.id, provider_activity_id=activity_id)
            self.session.add(activity)
        activity.provider_activity_id = activity_id
        activity.status, activity.attempts, activity.next_poll_at = "queued", 0, datetime.now(UTC)
        await self.session.commit()
        await self.session.refresh(analysis)
        return analysis, False

    async def poll(self, analysis: HeatAnalysis) -> HeatAnalysis:
        if not analysis.provider_activity_id:
            return analysis
        now = datetime.now(UTC)
        circuit = await self.session.scalar(
            select(ProviderCircuit).where(ProviderCircuit.provider == "fortyguard")
        )
        if circuit and circuit.is_open and circuit.open_until and circuit.open_until > now:
            return analysis
        previous_status = analysis.status
        try:
            raw = await self.client.get_activity(analysis.provider_activity_id)
            status, result = normalize_activity(raw)
            analysis.status, analysis.result = status, result
            if status is HeatAnalysisStatus.SUCCEEDED:
                analysis.source_updated_at = datetime.now(UTC)
                analysis.expires_at = datetime.now(UTC) + timedelta(seconds=self.cache_ttl_seconds)
            activity = await self.session.scalar(
                select(FortyGuardActivity).where(FortyGuardActivity.analysis_id == analysis.id)
            )
            if activity:
                activity.status, activity.last_payload, activity.attempts = (
                    status.value,
                    raw,
                    activity.attempts + 1,
                )
                activity.next_poll_at = (
                    None
                    if status in {HeatAnalysisStatus.SUCCEEDED, HeatAnalysisStatus.FAILED}
                    else now + timedelta(seconds=min(60, 2 ** min(activity.attempts, 5)))
                )
            if circuit:
                circuit.consecutive_failures, circuit.is_open, circuit.open_until = 0, False, None
            if status in {HeatAnalysisStatus.SUCCEEDED, HeatAnalysisStatus.FAILED} and status != previous_status:
                await record_audit_event(
                    self.session,
                    organization_id=analysis.organization_id,
                    actor_user_id=None,
                    event_type=f"heat_analysis.{status.value}",
                    resource_type="heat_analysis",
                    resource_id=analysis.id,
                    metadata={"provider": "fortyguard", "provider_activity_id": analysis.provider_activity_id or ""},
                )
        except FortyGuardError as exc:
            if circuit is None:
                circuit = ProviderCircuit(provider="fortyguard")
                self.session.add(circuit)
            circuit.consecutive_failures = (circuit.consecutive_failures or 0) + 1
            circuit.is_open = circuit.consecutive_failures >= 3
            circuit.open_until = now + timedelta(seconds=30) if circuit.is_open else None
            activity = await self.session.scalar(
                select(FortyGuardActivity).where(FortyGuardActivity.analysis_id == analysis.id)
            )
            if activity and activity.attempts + 1 < self.client.max_attempts and exc.retryable:
                activity.attempts += 1
                activity.status = "retrying"
                activity.next_poll_at = now + timedelta(seconds=min(60, 2**activity.attempts))
                analysis.status, analysis.error_code, analysis.error_message = (
                    HeatAnalysisStatus.RUNNING,
                    exc.code,
                    exc.message,
                )
            else:
                analysis.status, analysis.error_code, analysis.error_message = (
                    HeatAnalysisStatus.FAILED,
                    exc.code,
                    exc.message,
                )
            if analysis.status is HeatAnalysisStatus.FAILED and previous_status is not HeatAnalysisStatus.FAILED:
                await record_audit_event(
                    self.session,
                    organization_id=analysis.organization_id,
                    actor_user_id=None,
                    event_type="heat_analysis.failed",
                    resource_type="heat_analysis",
                    resource_id=analysis.id,
                    metadata={"provider": "fortyguard", "error_code": exc.code},
                )
        await self.session.commit()
        await self.session.refresh(analysis)
        return analysis
