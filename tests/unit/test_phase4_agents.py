from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agents.providers import AgentOutput, DeterministicProvider
from app.agents.runtime import (
    AGENT_NAMES,
    CoolProofState,
    build_graph,
    compile_langgraph,
    create_run,
    decide_run,
    execute_run,
)
from app.core.config import Settings
from app.db.base import Base
from app.db.models import (
    AgentApproval,
    AgentEvent,
    AgentRunStatus,
    Membership,
    Organization,
    Role,
    User,
)


class FakeProvider:
    async def complete(self, *, agent: str, context: dict[str, object]) -> AgentOutput:
        return AgentOutput(summary=f"{agent} summary", facts={"agent": agent}, citations=[f"cite:{agent}"])


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_graph_has_exactly_four_nodes() -> None:
    graph = build_graph(FakeProvider())
    assert tuple(graph) == AGENT_NAMES
    state = CoolProofState(run_id="r", organization_id="o")
    for name in AGENT_NAMES:
        state = await graph[name](state)
    assert tuple(state.summaries) == AGENT_NAMES
    assert len(state.citations) == 4


def test_langgraph_compiles() -> None:
    compiled = compile_langgraph(DeterministicProvider())
    assert compiled is not None


@pytest.mark.asyncio
async def test_run_checkpoints_and_manager_decision(session_factory) -> None:
    async with session_factory() as session:
        organization = Organization(name="Test", slug=f"test-{uuid4()}")
        user = User(cognito_subject=f"subject-{uuid4()}")
        session.add_all([organization, user])
        await session.flush()
        session.add(Membership(organization_id=organization.id, user_id=user.id, role=Role.MANAGER))
        run = await create_run(session, organization_id=organization.id, project_id=None, input_data={"zone": "z"})
        await execute_run(session, run, Settings(environment="test", database_url="sqlite+aiosqlite:///:memory"))
        assert run.status is AgentRunStatus.WAITING_APPROVAL
        events = (await session.scalars(select(AgentEvent).where(AgentEvent.run_id == run.id))).all()
        assert [event.node for event in events if event.event_type == "node.completed"] == list(AGENT_NAMES)
        approval = await decide_run(
            session, run, organization_id=organization.id, reviewer_user_id=user.id,
            reviewer_role=Role.MANAGER, decision="approve", comment="checked",
        )
        assert approval.decision == "approve"
        assert run.status is AgentRunStatus.APPROVED
        assert await session.scalar(select(AgentApproval).where(AgentApproval.run_id == run.id))
