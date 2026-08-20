from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import TenantContext, require_tenant_roles
from app.core.errors import APIError
from app.db.models import Role
from app.db.phase3_models import PortfolioRun
from app.db.session import get_db_session
from app.optimization.portfolio import ZoneDemand, optimize_portfolio
from app.services.interventions import InterventionSpec

router = APIRouter(prefix="/api/v1/portfolio-runs", tags=["optimization"])


class ZoneInput(BaseModel):
    zone_id: str
    land_use: str
    equity_priority: bool = False
    is_school: bool = False
    exposure_score: float = Field(default=0, ge=0)
    implementation_capacity: int = Field(default=1, ge=0)


class InterventionInput(BaseModel):
    intervention_id: str
    name: str
    unit_cost: float = Field(gt=0)
    cooling_score: float = Field(ge=0)
    eligible_land_uses: list[str] = Field(min_length=1)
    uncertainty: float = Field(default=0, ge=0)
    compatibility_group: str | None = None


class OptimizeRequest(BaseModel):
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
    result = optimize_portfolio(
        [ZoneDemand(**zone.model_dump()) for zone in request.zones],
        [
            InterventionSpec(
                intervention_id=item.intervention_id,
                name=item.name,
                unit_cost=item.unit_cost,
                cooling_score=item.cooling_score,
                eligible_land_uses=frozenset(item.eligible_land_uses),
                uncertainty=item.uncertainty,
                compatibility_group=item.compatibility_group,
            )
            for item in request.interventions
        ],
        request.budget,
        min_equity_units=request.min_equity_units,
        min_school_units=request.min_school_units,
        uncertainty_penalty=request.uncertainty_penalty,
        required={(x["zone_id"], x["intervention_id"]) for x in request.required},
        incompatible={(x["zone_id"], x["intervention_id"]) for x in request.incompatible},
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
        organization_id=tenant.organization.id, budget=request.budget, result_json=response
    )
    session.add(run)
    await session.commit()
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
    return {
        "portfolio_run_id": str(run.id),
        "project_id": str(run.project_id) if run.project_id else None,
        "budget": run.budget,
        "status": run.status,
        "result": run.result_json,
    }
