from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import TenantContext, require_tenant_roles
from app.core.errors import APIError
from app.db.models import Project, Role, Zone
from app.db.phase3_models import Intervention, PortfolioAllocation, PortfolioRun
from app.db.session import get_db_session
from app.optimization.portfolio import ZoneDemand, optimize_portfolio
from app.services.interventions import InterventionSpec

router = APIRouter(prefix="/api/v1/portfolio-runs", tags=["optimization"])


class ZoneInput(BaseModel):
    zone_id: UUID
    land_use: str
    equity_priority: bool = False
    is_school: bool = False
    exposure_score: float = Field(default=0, ge=0)
    implementation_capacity: int = Field(default=1, ge=0)


class InterventionInput(BaseModel):
    intervention_id: UUID
    name: str
    unit_cost: float = Field(gt=0)
    cooling_score: float = Field(ge=0)
    eligible_land_uses: list[str] = Field(min_length=1)
    uncertainty: float = Field(default=0, ge=0)
    compatibility_group: str | None = None


class OptimizeRequest(BaseModel):
    # A portfolio is an auditable project artifact.  Requiring the project
    # here prevents allocations from becoming tenant-wide orphan records.
    project_id: UUID
    budget: float = Field(ge=0)
    zones: list[ZoneInput] = Field(min_length=1)
    interventions: list[InterventionInput] = Field(min_length=1)
    min_equity_units: int = Field(default=0, ge=0)
    min_school_units: int = Field(default=0, ge=0)
    uncertainty_penalty: float = Field(default=0, ge=0)
    required: list[dict[str, str]] = Field(default_factory=list)
    incompatible: list[dict[str, str]] = Field(default_factory=list)


@router.post("")
async def optimize(
    request: OptimizeRequest,
    tenant: TenantContext = Depends(require_tenant_roles(Role.ANALYST, Role.MANAGER, Role.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    project = await session.scalar(
        select(Project).where(
            Project.id == request.project_id,
            Project.organization_id == tenant.organization.id,
        )
    )
    if project is None:
        raise APIError(404, "project_not_found", "Project was not found")

    # Zone and intervention IDs are persisted foreign keys, so validate every
    # submitted ID against the active tenant before invoking the solver.  The
    # request still carries scenario attributes (land use, exposure, and
    # capacity), while catalogue economics come from the tenant's catalogue.
    zone_ids = [zone.zone_id for zone in request.zones]
    if len(set(zone_ids)) != len(zone_ids):
        raise APIError(422, "duplicate_zone", "Each zone may appear only once")
    zone_result = await session.execute(
        select(Zone).where(
            Zone.id.in_(zone_ids),
            Zone.project_id == project.id,
            Zone.organization_id == tenant.organization.id,
        )
    )
    zones_by_id = {zone.id: zone for zone in zone_result.scalars().all()}
    if len(zones_by_id) != len(zone_ids):
        raise APIError(404, "zone_not_found", "One or more project zones were not found")

    intervention_ids = [item.intervention_id for item in request.interventions]
    if len(set(intervention_ids)) != len(intervention_ids):
        raise APIError(422, "duplicate_intervention", "Each intervention may appear only once")
    intervention_result = await session.execute(
        select(Intervention).where(
            Intervention.id.in_(intervention_ids),
            Intervention.organization_id == tenant.organization.id,
            Intervention.active.is_(True),
        )
    )
    interventions_by_id = {item.id: item for item in intervention_result.scalars().all()}
    if len(interventions_by_id) != len(intervention_ids):
        raise APIError(
            404, "intervention_not_found", "One or more active interventions were not found"
        )

    result = optimize_portfolio(
        [
            ZoneDemand(
                zone_id=str(zone.zone_id),
                land_use=zone.land_use,
                equity_priority=zone.equity_priority,
                is_school=zone.is_school,
                exposure_score=zone.exposure_score,
                implementation_capacity=zone.implementation_capacity,
            )
            for zone in request.zones
        ],
        [
            InterventionSpec(
                intervention_id=str(item.intervention_id),
                name=interventions_by_id[item.intervention_id].name,
                unit_cost=interventions_by_id[item.intervention_id].unit_cost,
                cooling_score=interventions_by_id[item.intervention_id].cooling_score,
                eligible_land_uses=frozenset(
                    interventions_by_id[item.intervention_id].eligible_land_uses
                ),
                uncertainty=item.uncertainty,
                compatibility_group=item.compatibility_group,
            )
            for item in request.interventions
        ],
        request.budget,
        min_equity_units=request.min_equity_units,
        min_school_units=request.min_school_units,
        uncertainty_penalty=request.uncertainty_penalty,
        required={(str(x["zone_id"]), str(x["intervention_id"])) for x in request.required},
        incompatible={(str(x["zone_id"]), str(x["intervention_id"])) for x in request.incompatible},
    )
    response: dict[str, object] = {
        "status": "completed",
        "total_cost": result.total_cost,
        "total_benefit": result.total_benefit,
        "total_uncertainty": result.total_uncertainty,
        "remaining_budget": result.remaining_budget,
        "rejected": list(result.rejected),
        "binding_constraints": list(result.binding_constraints),
        "allocations": [allocation.__dict__ for allocation in result.allocations],
    }
    run = PortfolioRun(
        organization_id=tenant.organization.id,
        project_id=project.id,
        budget=request.budget,
        result_json=response,
    )
    session.add(run)
    await session.flush()
    for allocation in result.allocations:
        session.add(
            PortfolioAllocation(
                organization_id=tenant.organization.id,
                portfolio_run_id=run.id,
                zone_id=UUID(allocation.zone_id),
                intervention_id=UUID(allocation.intervention_id),
                quantity=allocation.units,
                cost=allocation.cost,
            )
        )
    await session.commit()
    response["project_id"] = str(project.id)
    response["portfolio_run_id"] = str(run.id)
    return response


@router.get("/{portfolio_run_id}")
async def get_portfolio_run(
    portfolio_run_id: UUID,
    tenant: TenantContext = Depends(
        require_tenant_roles(Role.VIEWER, Role.ANALYST, Role.MANAGER, Role.ADMIN)
    ),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    """Return a portfolio run only when it belongs to the active tenant."""
    run = await session.scalar(
        select(PortfolioRun).where(
            PortfolioRun.id == portfolio_run_id,
            PortfolioRun.organization_id == tenant.organization.id,
        )
    )
    if run is None:
        raise APIError(404, "portfolio_run_not_found", "Portfolio run was not found")
    allocations_result = await session.execute(
        select(PortfolioAllocation)
        .where(
            PortfolioAllocation.portfolio_run_id == run.id,
            PortfolioAllocation.organization_id == tenant.organization.id,
        )
        .order_by(PortfolioAllocation.created_at)
    )
    allocations = [
        {
            "zone_id": str(allocation.zone_id),
            "intervention_id": str(allocation.intervention_id),
            "units": allocation.quantity,
            "cost": allocation.cost,
        }
        for allocation in allocations_result.scalars().all()
    ]
    return {
        "portfolio_run_id": str(run.id),
        "project_id": str(run.project_id) if run.project_id else None,
        "budget": run.budget,
        "status": run.status,
        "result": run.result_json,
        "allocations": allocations,
    }
