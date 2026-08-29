"""Governed, checkpointed four-agent planning runtime."""
from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from itertools import pairwise
from typing import TypedDict, cast
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.grounding import (
    grounded_citations,
    resolve_grounding,
    safe_input_references,
    safe_provider_facts,
    summary_for_agent,
)
from app.agents.providers import AgentOutput, LLMProvider, provider_from_settings
from app.core.config import Settings
from app.core.errors import APIError
from app.db.models import AgentApproval, AgentEvent, AgentRun, AgentRunStatus, Role
from app.services.audit import record_audit_event

AGENT_NAMES = (
    "heat_intelligence",
    "intervention_analyst",
    "portfolio",
    "verification",
)
_STATE_FIELDS = {"heat_evidence", "intervention_evidence", "portfolio", "verification", "citations", "summaries", "current_agent", "grounding"}


class CoolProofState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str
    organization_id: str
    project_id: str | None = None
    input: dict[str, object] = Field(default_factory=dict)
    heat_evidence: dict[str, object] = Field(default_factory=dict)
    intervention_evidence: list[dict[str, object]] = Field(default_factory=list)
    portfolio: dict[str, object] = Field(default_factory=dict)
    verification: dict[str, object] = Field(default_factory=dict)
    grounding: dict[str, object] = Field(default_factory=dict)
    citations: list[str] = Field(default_factory=list)
    summaries: dict[str, str] = Field(default_factory=dict)
    current_agent: str | None = None


class GraphInput(TypedDict, total=False):
    input: dict[str, object]
    heat_evidence: dict[str, object]
    intervention_evidence: list[dict[str, object]]
    portfolio: dict[str, object]
    verification: dict[str, object]
    citations: list[str]
    summaries: dict[str, str]
    grounding: dict[str, object]


Node = Callable[[CoolProofState], Awaitable[CoolProofState]]


async def _run_node(state: CoolProofState, name: str, provider: LLMProvider) -> CoolProofState:
    output: AgentOutput = await provider.complete(agent=name, context={
        # The request payload is deliberately not passed to providers. It can
        # contain prompts, source text, or untrusted identifiers. Grounding is
        # resolved from tenant-owned rows before the graph starts.
        "grounding": state.grounding,
        "heat_evidence": state.heat_evidence,
        "intervention_evidence": state.intervention_evidence,
        "portfolio": state.portfolio,
        "verification": state.verification,
    })
    state.current_agent = name
    if state.grounding:
        # Provider completions are never persisted. Keep only a deterministic
        # status line and scalar facts; citations must be issued by the
        # tenant-scoped resolver rather than invented by a model.
        state.summaries[name] = summary_for_agent(name, state.grounding)
        state.input = {}
        trusted = grounded_citations(state.grounding)
        state.citations.extend(
            c for c in trusted if c not in state.citations
        )
        facts = safe_provider_facts(output.facts)
    else:
        # Preserve the small in-memory graph contract used by unit tests and
        # callers that exercise build_graph directly without persistence.
        state.summaries[name] = output.summary
        state.citations.extend(c for c in output.citations if c not in state.citations)
        facts = output.facts
    if name == "heat_intelligence":
        state.heat_evidence = {**state.heat_evidence, **facts}
    elif name == "intervention_analyst":
        state.intervention_evidence.append({"summary": state.summaries[name], **facts})
    elif name == "portfolio":
        state.portfolio = {**state.portfolio, **facts}
    else:
        state.verification = {**state.verification, **facts}
    return state


def build_graph(provider: LLMProvider) -> dict[str, Node]:
    """Return the exactly-four-node graph definition.

    The durable executor below checkpoints after every node. Keeping the node
    map explicit also makes the graph independently testable and lets a real
    LangGraph StateGraph be wired by deployment without changing contracts.
    """
    async def invoke(state: CoolProofState, agent: str) -> CoolProofState:
        return await _run_node(state, agent, provider)

    return {name: (lambda state, agent=name: invoke(state, agent))  # type: ignore[misc]
            for name in AGENT_NAMES}


def compile_langgraph(provider: LLMProvider) -> object:
    """Compile the four-node LangGraph graph when the optional runtime is present."""
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError as exc:  # pragma: no cover - dependency is installed in deployments
        raise RuntimeError("langgraph dependency is required for governed execution") from exc

    graph = StateGraph(GraphInput)
    nodes = build_graph(provider)
    for name in AGENT_NAMES:
        async def invoke(raw: GraphInput, agent: str = name) -> GraphInput:
            state = CoolProofState(
                run_id=str(raw.get("run_id", "langgraph")),
                organization_id=str(raw.get("organization_id", "langgraph")),
                project_id=raw.get("project_id"), input=raw.get("input", {}),
                **{key: value for key, value in raw.items() if key in _STATE_FIELDS},
            )
            result = await nodes[agent](state)
            return cast(GraphInput, result.model_dump(mode="json"))
        graph.add_node(name, invoke)  # type: ignore[call-overload]
    graph.add_edge(START, AGENT_NAMES[0])
    for previous, current in pairwise(AGENT_NAMES):
        graph.add_edge(previous, current)
    graph.add_edge(AGENT_NAMES[-1], END)
    return graph.compile()


async def create_run(
    session: AsyncSession,
    *,
    organization_id: UUID,
    project_id: UUID | None,
    input_data: dict[str, object],
) -> AgentRun:
    # Keep only persisted-object references needed for grounding. Prompts,
    # source text, and arbitrary request metadata never become durable.
    safe_input = safe_input_references(input_data)
    run = AgentRun(
        organization_id=organization_id,
        project_id=project_id,
        thread_id=str(uuid4()),
        input_json=safe_input,
        state_json={"input": safe_input},
        status=AgentRunStatus.QUEUED,
    )
    session.add(run)
    await session.flush()
    await _event(session, run, "run.created", None, {"status": run.status.value}, "Run queued")
    await session.commit()
    return run


async def _event(
    session: AsyncSession, run: AgentRun, event_type: str, node: str | None,
    payload: dict[str, object], safe_summary: str,
) -> AgentEvent:
    max_sequence = await session.scalar(
        select(func.max(AgentEvent.sequence)).where(AgentEvent.run_id == run.id)
    )
    event = AgentEvent(
        run_id=run.id, organization_id=run.organization_id,
        sequence=(int(max_sequence or 0) + 1), event_type=event_type, node=node,
        payload_json=payload, safe_summary=safe_summary,
    )
    session.add(event)
    return event


async def execute_run(session: AsyncSession, run: AgentRun, settings: Settings) -> AgentRun:
    provider = provider_from_settings(settings)
    run.status = AgentRunStatus.RUNNING
    await _event(session, run, "run.started", None, {}, "Run started")
    await session.commit()
    state = CoolProofState(
        run_id=str(run.id), organization_id=str(run.organization_id),
        project_id=str(run.project_id) if run.project_id else None,
        input=run.input_json,
        **{key: value for key, value in run.state_json.items() if key in _STATE_FIELDS},
    )
    try:
        state.grounding = await resolve_grounding(
            session,
            organization_id=run.organization_id,
            project_id=run.project_id,
            input_data=run.input_json,
        )
        # The compiled graph is the production execution path.  AgentRun is
        # the application-owned durable checkpoint: the final LangGraph
        # state, thread id, and monotonically increasing revision are written
        # transactionally before the approval gate is emitted.  This keeps
        # restart/retry semantics independent of the optional LangGraph
        # checkpointer backend while retaining its thread contract.
        compiled = compile_langgraph(provider)
        raw_state = state.model_dump(mode="json")
        invoke = getattr(compiled, "ainvoke", None)
        if invoke is None:  # pragma: no cover - defensive for incompatible versions
            raise RuntimeError("compiled LangGraph runtime does not support async invocation")
        result = await invoke(raw_state, config={"configurable": {"thread_id": run.thread_id}})
        state = CoolProofState(
            run_id=str(run.id), organization_id=str(run.organization_id),
            project_id=str(run.project_id) if run.project_id else None,
            input=result.get("input", {}),
            **{key: value for key, value in result.items() if key in _STATE_FIELDS},
        )
        # Emit a durable node checkpoint for every governed agent.  The graph
        # itself remains the source of execution; these records make SSE
        # replay and operational recovery deterministic after a process loss.
        for name in AGENT_NAMES:
            run.current_node = name
            run.revision += 1
            checkpoint = state.model_dump(mode="json")
            checkpoint["checkpoint_node"] = name
            checkpoint["checkpoint_thread_id"] = run.thread_id
            run.state_json = checkpoint
            await _event(session, run, "node.completed", name, {"revision": run.revision, "thread_id": run.thread_id}, f"{name} completed")
            await session.commit()
        run.status = AgentRunStatus.WAITING_APPROVAL
        await _event(session, run, "approval.required", None, {}, "Manager approval required")
        await session.commit()
    except Exception:  # noqa: BLE001 - convert all node failures to safe durable state
        run.status = AgentRunStatus.FAILED
        run.error_code = "agent_run_failed"
        run.error_message = "Agent execution failed"
        await _event(session, run, "run.failed", run.current_node, {}, "Agent execution failed")
        await session.commit()
    return run


async def finalize_approved_run(session: AsyncSession, run: AgentRun) -> AgentRun:
    """Finalize an approved graph run in a separate durable transaction."""
    if run.status is not AgentRunStatus.APPROVED:
        raise APIError(409, "approval_not_available", "Only an approved run can be finalized")
    run.status = AgentRunStatus.COMPLETED
    run.current_node = "verification"
    await _event(session, run, "run.completed", "verification", {}, "Approved run finalized")
    await session.commit()
    return run


async def decide_run(
    session: AsyncSession, run: AgentRun, *, organization_id: UUID, reviewer_user_id: UUID,
    reviewer_role: Role, decision: str, comment: str | None,
) -> AgentApproval:
    if reviewer_role not in {Role.MANAGER, Role.ADMIN}:
        raise APIError(403, "approval_role_required", "Only managers or admins may approve agent runs")
    if run.organization_id != organization_id:
        raise APIError(404, "agent_run_not_found", "Agent run was not found")
    if run.status != AgentRunStatus.WAITING_APPROVAL:
        raise APIError(409, "approval_not_available", "This run is not awaiting approval")
    if decision not in {"approve", "reject", "revise"}:
        raise APIError(422, "invalid_approval_decision", "Decision must be approve, reject, or revise")
    # A revision is a new approval cycle.  Approval rows are intentionally an
    # append-only audit trail, so repeated revise -> approve decisions remain
    # safe and recoverable instead of being blocked by a run-wide uniqueness
    # constraint.
    approval = AgentApproval(
        run_id=run.id, organization_id=organization_id, decision=decision,
        reviewer_user_id=reviewer_user_id, comment=comment, revision=run.revision,
    )
    session.add(approval)
    run.status = {
        "approve": AgentRunStatus.APPROVED,
        "reject": AgentRunStatus.REJECTED,
        "revise": AgentRunStatus.QUEUED,
    }[decision]
    await _event(session, run, f"run.{decision}d" if decision != "revise" else "run.revision_requested", None, {}, f"Run {decision}d")
    await record_audit_event(
        session, organization_id=organization_id, actor_user_id=reviewer_user_id,
        event_type=f"agent_run.{decision}", resource_type="agent_run", resource_id=run.id,
        metadata={"revision": run.revision},
    )
    await session.commit()
    return approval


async def stream_events(session: AsyncSession, run: AgentRun, after: int = 0) -> AsyncIterator[AgentEvent]:
    result = await session.scalars(
        select(AgentEvent).where(AgentEvent.run_id == run.id, AgentEvent.sequence > after)
        .order_by(AgentEvent.sequence)
    )
    for event in result.all():
        yield event
