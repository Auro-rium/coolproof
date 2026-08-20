from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import TenantContext, require_tenant_roles
from app.core.errors import APIError
from app.db.models import Project, Role, Zone
from app.db.session import get_db_session
from app.services.audit import record_audit_event

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class ZoneCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    geometry: dict[str, object]


def project_out(project: Project) -> dict[str, object]:
    return {"id": str(project.id), "name": project.name, "description": project.description}


def zone_out(zone: Zone) -> dict[str, object]:
    return {
        "id": str(zone.id),
        "project_id": str(zone.project_id),
        "name": zone.name,
        "geometry": zone.geometry,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreate,
    tenant: TenantContext = Depends(require_tenant_roles(Role.ANALYST, Role.MANAGER, Role.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    project = Project(organization_id=tenant.organization.id, **body.model_dump())
    session.add(project)
    await session.flush()
    await record_audit_event(
        session,
        organization_id=tenant.organization.id,
        actor_user_id=tenant.user.id,
        event_type="project.created",
        resource_type="project",
        resource_id=project.id,
    )
    await session.commit()
    await session.refresh(project)
    return project_out(project)


@router.get("")
async def list_projects(
    tenant: TenantContext = Depends(
        require_tenant_roles(Role.VIEWER, Role.ANALYST, Role.MANAGER, Role.ADMIN)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> list[dict[str, object]]:
    return [
        project_out(item)
        for item in (
            await session.scalars(
                select(Project)
                .where(Project.organization_id == tenant.organization.id)
                .order_by(Project.created_at.desc())
            )
        ).all()
    ]


async def _project(project_id: UUID, tenant: TenantContext, session: AsyncSession) -> Project:
    project = await session.scalar(
        select(Project).where(
            Project.id == project_id, Project.organization_id == tenant.organization.id
        )
    )
    if not project:
        raise APIError(404, "project_not_found", "Project was not found")
    return project


@router.post("/{project_id}/zones", status_code=status.HTTP_201_CREATED)
async def create_zone(
    project_id: UUID,
    body: ZoneCreate,
    tenant: TenantContext = Depends(require_tenant_roles(Role.ANALYST, Role.MANAGER, Role.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    await _project(project_id, tenant, session)
    zone = Zone(organization_id=tenant.organization.id, project_id=project_id, **body.model_dump())
    session.add(zone)
    await session.flush()
    await record_audit_event(
        session,
        organization_id=tenant.organization.id,
        actor_user_id=tenant.user.id,
        event_type="zone.created",
        resource_type="zone",
        resource_id=zone.id,
        metadata={"project_id": str(project_id)},
    )
    await session.commit()
    await session.refresh(zone)
    return zone_out(zone)


@router.get("/{project_id}/zones")
async def list_zones(
    project_id: UUID,
    tenant: TenantContext = Depends(
        require_tenant_roles(Role.VIEWER, Role.ANALYST, Role.MANAGER, Role.ADMIN)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> list[dict[str, object]]:
    await _project(project_id, tenant, session)
    return [
        zone_out(item)
        for item in (
            await session.scalars(
                select(Zone).where(
                    Zone.project_id == project_id, Zone.organization_id == tenant.organization.id
                )
            )
        ).all()
    ]
