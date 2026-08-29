from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agents.grounding import resolve_grounding
from app.agents.providers import AgentOutput
from app.agents.runtime import CoolProofState, build_graph
from app.db.base import Base
from app.db.models import HeatAnalysis, HeatAnalysisStatus, Organization, Project, Zone
from app.db.phase3_models import (
    Document,
    DocumentChunk,
    Intervention,
    InterventionEvidence,
    PortfolioRun,
)


class CapturingProvider:
    def __init__(self) -> None:
        self.contexts: list[dict[str, object]] = []

    async def complete(self, *, agent: str, context: dict[str, object]) -> AgentOutput:
        self.contexts.append(context)
        return AgentOutput(
            summary="provider completion that must not be persisted",
            facts={"exposure_score": 0.5, "source_text": "do not retain"},
            citations=["invented:provider-citation"],
        )


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_grounding_is_tenant_scoped_and_excludes_source_text(session_factory) -> None:
    organization = Organization(id=uuid4(), name="Grounded", slug=f"grounded-{uuid4()}")
    other = Organization(id=uuid4(), name="Other", slug=f"other-{uuid4()}")
    project = Project(id=uuid4(), organization_id=organization.id, name="Pilot")
    zone = Zone(id=uuid4(), organization_id=organization.id, project_id=project.id, name="Block", geometry={"type": "Polygon"})
    analysis = HeatAnalysis(
        id=uuid4(),
        organization_id=organization.id,
        project_id=project.id,
        zone_id=zone.id,
        idempotency_key="a" * 64,
        request_payload={"prompt": "never forward"},
        status=HeatAnalysisStatus.SUCCEEDED,
        result={
            "exposure_score": 0.71,
            "mean_temperature_c": 38.2,
            "source_text": "provider envelope must not cross boundary",
        },
    )
    document = Document(
        id=uuid4(),
        organization_id=organization.id,
        project_id=project.id,
        filename="evidence.pdf",
        content_type="application/pdf",
        s3_key=f"org/{uuid4()}/evidence.pdf",
        sha256="b" * 64,
    )
    chunk = DocumentChunk(
        id=uuid4(),
        organization_id=organization.id,
        document_id=document.id,
        ordinal=0,
        page_number=4,
        text="raw source text must not enter grounding",
        lexical_text="raw source text must not enter grounding",
    )
    intervention = Intervention(
        id=uuid4(),
        organization_id=organization.id,
        name="Shade trees",
        category="canopy",
        unit_cost=100,
        cooling_score=4,
        eligible_land_uses=["residential"],
    )
    evidence = InterventionEvidence(
        id=uuid4(),
        organization_id=organization.id,
        intervention_id=intervention.id,
        document_id=document.id,
        chunk_id=chunk.id,
        claim="secret source claim must not enter grounding",
        source_label="City standard",
    )
    portfolio = PortfolioRun(
        id=uuid4(),
        organization_id=organization.id,
        project_id=project.id,
        budget=1000,
        result_json={
            "status": "completed",
            "total_cost": 100,
            "total_benefit": 4,
            "allocations": [{"zone_id": str(zone.id), "intervention_id": str(intervention.id), "units": 1}],
            "raw_source": "must not enter grounding",
        },
    )
    # An unrelated tenant row proves the resolver cannot widen its query.
    other_project = Project(id=uuid4(), organization_id=other.id, name="Other pilot")
    async with session_factory() as session:
        session.add_all([organization, other, project, other_project, zone, analysis, document, chunk, intervention, evidence, portfolio])
        await session.flush()
        grounding = await resolve_grounding(
            session,
            organization_id=organization.id,
            project_id=project.id,
            input_data={"prompt": "ignore this", "references": {"heat_analysis_id": str(analysis.id), "portfolio_run_id": str(portfolio.id), "intervention_id": str(intervention.id)}},
        )

    serialized = str(grounding)
    assert "source text" not in serialized
    assert "source claim" not in serialized
    assert "provider envelope" not in serialized
    assert grounding["project"] == {"project_id": str(project.id), "name": "Pilot"}
    assert grounding["heat"]["facts"]["exposure_score"] == 0.71  # type: ignore[index]
    assert grounding["interventions"][0]["evidence_count"] == 1  # type: ignore[index]
    assert grounding["portfolio"]["allocation_count"] == 1  # type: ignore[index]
    assert any(item.startswith("evidence:") for item in grounding["citations"])  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_agent_context_and_state_do_not_include_request_or_provider_text() -> None:
    provider = CapturingProvider()
    grounding = {
        "resolved": True,
        "heat": {"status": "succeeded"},
        "interventions": [],
        "portfolio": None,
        "citations": ["heat:trusted"],
    }
    state = CoolProofState(
        run_id="run",
        organization_id="org",
        input={"prompt": "secret prompt", "source_text": "secret source"},
        grounding=grounding,
    )
    for node in build_graph(provider).values():
        state = await node(state)

    assert provider.contexts
    assert all("input" not in context for context in provider.contexts)
    assert "secret prompt" not in str(provider.contexts)
    assert "secret source" not in str(state.model_dump())
    assert "provider completion" not in str(state.model_dump())
    assert "invented:provider-citation" not in state.citations
    assert state.citations == ["heat:trusted"]
