from __future__ import annotations

import hashlib
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import TenantContext, require_tenant_roles
from app.core.config import Settings, get_settings
from app.core.errors import APIError
from app.core.telemetry import emit_event
from app.db.models import Project, Role
from app.db.phase3_models import PortfolioRun, VerificationRun
from app.db.session import get_db_session
from app.services.reports import report_download_url, write_report
from app.services.verification import VerificationInput, calculate_verification

router = APIRouter(prefix="/api/v1/verifications", tags=["verification"])
reports_router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


class VerificationRequest(BaseModel):
    project_id: UUID | None = None
    portfolio_run_id: UUID | None = None
    treated_baseline: float = Field(ge=-100, le=100)
    treated_observed: float = Field(ge=-100, le=100)
    control_baseline: float = Field(ge=-100, le=100)
    control_observed: float = Field(ge=-100, le=100)
    treated_weather_delta: float = Field(default=0, ge=-100, le=100)
    control_weather_delta: float = Field(default=0, ge=-100, le=100)
    expected_cooling: float = Field(default=0, ge=0, le=100)
    treated_threshold_hours_baseline: float = Field(default=0, ge=0)
    treated_threshold_hours_observed: float = Field(default=0, ge=0)
    control_threshold_hours_baseline: float = Field(default=0, ge=0)
    control_threshold_hours_observed: float = Field(default=0, ge=0)
    total_cost: float = Field(default=0, ge=0)
    sample_size: int = Field(default=1, ge=1)


def _idempotency_key(request: VerificationRequest) -> str:
    canonical = json.dumps(request.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@router.post("", status_code=201)
async def create_verification(
    request: VerificationRequest,
    tenant: TenantContext = Depends(require_tenant_roles(Role.ANALYST, Role.MANAGER, Role.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    if request.project_id is not None:
        project = await session.scalar(
            select(Project).where(
                Project.id == request.project_id,
                Project.organization_id == tenant.organization.id,
            )
        )
        if project is None:
            raise APIError(404, "project_not_found", "Project was not found")
    if request.portfolio_run_id is not None:
        portfolio = await session.scalar(
            select(PortfolioRun).where(
                PortfolioRun.id == request.portfolio_run_id,
                PortfolioRun.organization_id == tenant.organization.id,
            )
        )
        if portfolio is None:
            raise APIError(404, "portfolio_run_not_found", "Portfolio run was not found")
        if (
            request.project_id is not None
            and portfolio.project_id is not None
            and portfolio.project_id != request.project_id
        ):
            raise APIError(
                422,
                "portfolio_project_mismatch",
                "Portfolio run does not belong to the selected project",
            )
    idempotency_key = _idempotency_key(request)
    existing = await session.scalar(
        select(VerificationRun).where(
            VerificationRun.organization_id == tenant.organization.id,
            VerificationRun.idempotency_key == idempotency_key,
        )
    )
    if existing:
        return _response(existing, settings)
    try:
        result = calculate_verification(VerificationInput(**request.model_dump(exclude={"project_id", "portfolio_run_id"})))
    except ValueError as exc:
        raise APIError(422, "invalid_observation", str(exc)) from exc
    run = VerificationRun(
        organization_id=tenant.organization.id,
        project_id=request.project_id,
        portfolio_run_id=request.portfolio_run_id,
        idempotency_key=idempotency_key,
        result_json=result,
    )
    session.add(run)
    await session.commit()
    try:
        run.report_s3_key = write_report(
            settings=settings,
            organization_id=tenant.organization.id,
            verification_id=run.id,
            result=result,
        )
        await session.commit()
    except (OSError, ValueError, RuntimeError):
        # The calculation remains durable; callers receive an explicit artifact
        # warning and can retry report generation after fixing S3.
        emit_event("verification_report_write", status="failed")
    return _response(run, settings)


@router.get("/{verification_id}")
async def get_verification(
    verification_id: UUID,
    tenant: TenantContext = Depends(require_tenant_roles(Role.VIEWER, Role.ANALYST, Role.MANAGER, Role.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    run = await session.get(VerificationRun, verification_id)
    if run is None or run.organization_id != tenant.organization.id:
        raise HTTPException(status_code=404, detail="Verification not found")
    return _response(run, settings)


@router.post("/{verification_id}/report")
async def create_report(
    verification_id: UUID,
    tenant: TenantContext = Depends(require_tenant_roles(Role.ANALYST, Role.MANAGER, Role.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    run = await session.get(VerificationRun, verification_id)
    if run is None or run.organization_id != tenant.organization.id:
        raise HTTPException(status_code=404, detail="Verification not found")
    try:
        run.report_s3_key = write_report(
            settings=settings,
            organization_id=tenant.organization.id,
            verification_id=run.id,
            result=run.result_json,
        )
    except Exception as exc:
        emit_event("verification_report_write", status="failed")
        raise APIError(503, "report_storage_unavailable", "Unable to create report artifact") from exc
    if not run.report_s3_key:
        raise APIError(503, "report_storage_unavailable", "Report storage is not configured")
    await session.commit()
    return {"verification_id": str(run.id), "report_key": run.report_s3_key, "status": "ready"}


def _response(run: VerificationRun, settings: Settings) -> dict[str, object]:
    report_url = None
    if run.report_s3_key:
        try:
            report_url = report_download_url(settings=settings, key=run.report_s3_key)
        except (OSError, ValueError, RuntimeError):
            report_url = None
    return {
        "verification_id": str(run.id),
        "status": run.status,
        "result": run.result_json,
        "report_key": run.report_s3_key,
        "report_url": report_url,
    }


class ReportRequest(BaseModel):
    verification_id: UUID


async def _get_tenant_verification(
    verification_id: UUID, tenant: TenantContext, session: AsyncSession
) -> VerificationRun:
    run = await session.scalar(
        select(VerificationRun).where(
            VerificationRun.id == verification_id,
            VerificationRun.organization_id == tenant.organization.id,
        )
    )
    if run is None:
        raise APIError(404, "verification_not_found", "Verification was not found")
    return run


async def _materialize_report(
    run: VerificationRun, tenant: TenantContext, session: AsyncSession, settings: Settings
) -> dict[str, object]:
    try:
        run.report_s3_key = write_report(
            settings=settings,
            organization_id=tenant.organization.id,
            verification_id=run.id,
            result=run.result_json,
        )
    except Exception as exc:
        emit_event("verification_report_write", status="failed")
        raise APIError(503, "report_storage_unavailable", "Unable to create report artifact") from exc
    if not run.report_s3_key:
        raise APIError(503, "report_storage_unavailable", "Report storage is not configured")
    await session.commit()
    return {"verification_id": str(run.id), "report_key": run.report_s3_key, "status": "ready"}


@reports_router.post("", status_code=201)
async def create_report_alias(
    request: ReportRequest,
    tenant: TenantContext = Depends(require_tenant_roles(Role.ANALYST, Role.MANAGER, Role.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    run = await _get_tenant_verification(request.verification_id, tenant, session)
    return await _materialize_report(run, tenant, session, settings)


@reports_router.get("/{verification_id}")
async def get_report_alias(
    verification_id: UUID,
    tenant: TenantContext = Depends(
        require_tenant_roles(Role.VIEWER, Role.ANALYST, Role.MANAGER, Role.ADMIN)
    ),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    run = await _get_tenant_verification(verification_id, tenant, session)
    return _response(run, settings)
