from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import TenantContext
from app.api.optimization import InterventionInput, OptimizeRequest, ZoneInput, optimize
from app.core.errors import APIError
from app.db.base import Base
from app.db.models import Membership, Organization, Project, Role, User, Zone
from app.db.phase3_models import Intervention, PortfolioAllocation, PortfolioRun


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


async def _tenant_fixture(session):
    organization = Organization(name="Test organization", slug=f"test-{uuid4().hex}")
    user = User(cognito_subject=f"subject-{uuid4().hex}")
    session.add_all([organization, user])
    await session.flush()
    membership = Membership(
        organization_id=organization.id, user_id=user.id, role=Role.ANALYST
    )
    session.add(membership)
    await session.flush()
    return TenantContext(organization=organization, user=user, membership=membership)


async def test_optimize_persists_project_scoped_allocations(db_session) -> None:
    tenant = await _tenant_fixture(db_session)
    project = Project(organization_id=tenant.organization.id, name="Summer pilot")
    zone = Zone(
        organization_id=tenant.organization.id,
        project_id=project.id,
        name="School block",
        geometry={"type": "Polygon", "coordinates": []},
    )
    intervention = Intervention(
        organization_id=tenant.organization.id,
        name="Shade trees",
        category="shade",
        unit_cost=100,
        cooling_score=8,
        eligible_land_uses=["civic"],
    )
    session = db_session
    session.add_all([project, intervention])
    await session.flush()
    zone.project_id = project.id
    session.add(zone)
    await session.flush()

    request = OptimizeRequest(
        project_id=project.id,
        budget=100,
        zones=[
            ZoneInput(
                zone_id=zone.id,
                land_use="civic",
                is_school=True,
                implementation_capacity=1,
            )
        ],
        interventions=[
            InterventionInput(
                intervention_id=intervention.id,
                name="ignored request label",
                unit_cost=999999,
                cooling_score=0,
                eligible_land_uses=["civic"],
            )
        ],
        min_school_units=1,
    )

    response = await optimize(request, tenant=tenant, session=session)

    run = await session.scalar(
        select(PortfolioRun).where(PortfolioRun.id == UUID(str(response["portfolio_run_id"])))
    )
    assert run is not None
    assert run.project_id == project.id
    allocations = (
        await session.scalars(
            select(PortfolioAllocation).where(PortfolioAllocation.portfolio_run_id == run.id)
        )
    ).all()
    assert len(allocations) == 1
    assert allocations[0].organization_id == tenant.organization.id
    assert allocations[0].zone_id == zone.id
    assert allocations[0].intervention_id == intervention.id
    assert allocations[0].quantity == 1
    assert allocations[0].cost == 100

    # The GET handler is exercised below without reaching through the router.
    from app.api.optimization import get_portfolio_run

    persisted = await get_portfolio_run(run.id, tenant=tenant, session=session)
    assert persisted["allocations"] == [
        {"zone_id": str(zone.id), "intervention_id": str(intervention.id), "units": 1, "cost": 100}
    ]


async def test_optimize_rejects_zone_from_another_project(db_session) -> None:
    tenant = await _tenant_fixture(db_session)
    other_project = Project(organization_id=tenant.organization.id, name="Other project")
    project = Project(organization_id=tenant.organization.id, name="Selected project")
    session = db_session
    session.add_all([other_project, project])
    await session.flush()
    zone = Zone(
        organization_id=tenant.organization.id,
        project_id=other_project.id,
        name="Wrong project zone",
        geometry={"type": "Polygon", "coordinates": []},
    )
    intervention = Intervention(
        organization_id=tenant.organization.id,
        name="Shade trees",
        category="shade",
        unit_cost=100,
        cooling_score=8,
        eligible_land_uses=["civic"],
    )
    session.add_all([zone, intervention])
    await session.flush()
    request = OptimizeRequest(
        project_id=project.id,
        budget=100,
        zones=[ZoneInput(zone_id=zone.id, land_use="civic")],
        interventions=[
            InterventionInput(
                intervention_id=intervention.id,
                name=intervention.name,
                unit_cost=intervention.unit_cost,
                cooling_score=intervention.cooling_score,
                eligible_land_uses=intervention.eligible_land_uses,
            )
        ],
    )

    with pytest.raises(APIError) as raised:
        await optimize(request, tenant=tenant, session=session)
    assert raised.value.code == "zone_not_found"
