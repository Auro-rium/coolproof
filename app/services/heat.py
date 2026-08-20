from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FortyGuardActivity, HeatAnalysis, HeatAnalysisStatus, ProviderCircuit
from app.integrations.fortyguard import FortyGuardClient, FortyGuardError
from app.services.audit import record_audit_event


def analysis_idempotency_key(zone_id: UUID, request: dict[str, object]) -> str:
    canonical = json.dumps(
        {"zone_id": str(zone_id), "request": request}, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def normalize_activity(
    payload: dict[str, Any],
) -> tuple[HeatAnalysisStatus, dict[str, object] | None]:
    state = str(payload.get("status", "")).lower()
    if state in {"queued", "pending"}:
        return HeatAnalysisStatus.QUEUED, None
    if state in {"running", "processing"}:
        return HeatAnalysisStatus.RUNNING, None
    if state in {"succeeded", "completed", "complete"}:
        result = payload.get("result") or payload.get("data")
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
        analysis = HeatAnalysis(
            organization_id=organization_id,
            project_id=project_id,
            zone_id=zone_id,
            idempotency_key=key,
            request_payload=payload,
        )
        self.session.add(analysis)
        await self.session.flush()
        try:
            activity_id = await self.client.create_analysis(payload)
        except FortyGuardError as exc:
            analysis.status, analysis.error_code, analysis.error_message = (
                HeatAnalysisStatus.FAILED,
                exc.code,
                exc.message,
            )
            await self.session.commit()
            raise
        analysis.provider_activity_id = activity_id
        self.session.add(
            FortyGuardActivity(
                analysis_id=analysis.id,
                provider_activity_id=activity_id,
                status="queued",
                next_poll_at=datetime.now(UTC),
            )
        )
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
            circuit.consecutive_failures += 1
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
