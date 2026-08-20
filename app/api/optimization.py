from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import TenantContext, require_tenant_roles
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


class InterventionInput(BaseModel):
    intervention_id: str
    name: str
    unit_cost: float = Field(gt=0)
    cooling_score: float = Field(ge=0)
    eligible_land_uses: list[str] = Field(min_length=1)


class OptimizeRequest(BaseModel):
    budget: float = Field(ge=0)
    zones: list[ZoneInput] = Field(min_length=1)
    interventions: list[InterventionInput] = Field(min_length=1)
    min_equity_units: int = Field(default=0, ge=0)
    min_school_units: int = Field(default=0, ge=0)


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
            )
            for item in request.interventions
        ],
        request.budget,
        min_equity_units=request.min_equity_units,
        min_school_units=request.min_school_units,
    )
    response: dict[str, object] = {
        "status": "completed",
        "total_cost": result.total_cost,
        "total_benefit": result.total_benefit,
        "allocations": [allocation.__dict__ for allocation in result.allocations],
    }
    run = PortfolioRun(
        organization_id=tenant.organization.id, budget=request.budget, result_json=response
    )
    session.add(run)
    await session.commit()
    response["portfolio_run_id"] = str(run.id)
    return response
