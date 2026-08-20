from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import TenantContext, require_tenant_roles
from app.core.config import Settings, get_settings
from app.core.errors import APIError
from app.db.models import HeatAnalysis, Project, Role, Zone
from app.db.session import get_db_session
from app.integrations.fortyguard import FortyGuardClient, FortyGuardError
from app.services.audit import record_audit_event
from app.services.heat import HeatService
from app.workers.heat_queue import RedisHeatQueue

router = APIRouter(prefix="/api/v1", tags=["heat"])


class HeatAnalysisCreate(BaseModel):
    project_id: UUID
    zone_id: UUID
    parameters: dict[str, object] = Field(default_factory=dict)


def heat_out(analysis: HeatAnalysis, *, cached: bool = False) -> dict[str, object]:
    return {
        "id": str(analysis.id),
        "project_id": str(analysis.project_id),
        "zone_id": str(analysis.zone_id),
        "status": analysis.status.value,
        "result": analysis.result,
        "cached": cached,
        "stale": bool(
            analysis.expires_at
            and analysis.expires_at
            <= __import__("datetime").datetime.now(__import__("datetime").UTC)
        ),
        "error": {"code": analysis.error_code, "message": analysis.error_message}
        if analysis.error_code
        else None,
    }


async def _zone(body: HeatAnalysisCreate, tenant: TenantContext, session: AsyncSession) -> Zone:
    project = await session.scalar(
        select(Project).where(
            Project.id == body.project_id, Project.organization_id == tenant.organization.id
        )
    )
    zone = await session.scalar(
        select(Zone).where(
            Zone.id == body.zone_id,
            Zone.project_id == body.project_id,
            Zone.organization_id == tenant.organization.id,
        )
    )
    if not project or not zone:
        raise APIError(404, "zone_not_found", "Project zone was not found")
    return zone


@router.post("/heat-analyses", status_code=status.HTTP_202_ACCEPTED)
async def create_heat_analysis(
    body: HeatAnalysisCreate,
    tenant: TenantContext = Depends(require_tenant_roles(Role.ANALYST, Role.MANAGER, Role.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    zone = await _zone(body, tenant, session)
    payload: dict[str, object] = {"geometry": zone.geometry, "parameters": body.parameters}
    client = FortyGuardClient(
        settings.fortyguard_base_url,
        settings.fortyguard_api_key.get_secret_value() if settings.fortyguard_api_key else None,
        timeout=settings.fortyguard_timeout_seconds,
        max_attempts=settings.fortyguard_max_attempts,
    )
    try:
        analysis, cached = await HeatService(
            session, client, settings.heat_cache_ttl_seconds
        ).submit(
            organization_id=tenant.organization.id,
            project_id=body.project_id,
            zone_id=body.zone_id,
            payload=payload,
        )
    except FortyGuardError as exc:
        raise APIError(503, exc.code, exc.message) from exc
    if not cached:
        await record_audit_event(
            session,
            organization_id=tenant.organization.id,
            actor_user_id=tenant.user.id,
            event_type="heat_analysis.requested",
            resource_type="heat_analysis",
            resource_id=analysis.id,
            metadata={"zone_id": str(body.zone_id)},
        )
        await session.commit()
        if settings.redis_url:
            redis = Redis.from_url(settings.redis_url)
            try:
                await RedisHeatQueue(redis).enqueue(analysis.id)
            finally:
                await redis.close()
    return heat_out(analysis, cached=cached)


@router.get("/heat-analyses/{analysis_id}")
async def get_heat_analysis(
    analysis_id: UUID,
    tenant: TenantContext = Depends(
        require_tenant_roles(Role.VIEWER, Role.ANALYST, Role.MANAGER, Role.ADMIN)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    analysis = await session.scalar(
        select(HeatAnalysis).where(
            HeatAnalysis.id == analysis_id, HeatAnalysis.organization_id == tenant.organization.id
        )
    )
    if not analysis:
        raise APIError(404, "heat_analysis_not_found", "Heat analysis was not found")
    return heat_out(analysis)
