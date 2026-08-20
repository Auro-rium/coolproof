from __future__ import annotations

import json
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.runtime import (
    create_run,
    decide_run,
    execute_run,
    finalize_approved_run,
    stream_events,
)
from app.api.deps import TenantContext, require_tenant_roles
from app.core.config import Settings, get_settings
from app.core.errors import APIError
from app.db.models import AgentRun, Project, Role
from app.db.session import get_db_session

router = APIRouter(prefix="/api/v1/agent-runs", tags=["agents"])


class CreateAgentRunRequest(BaseModel):
    project_id: UUID | None = None
    input: dict[str, object] = Field(default_factory=dict)


class ApprovalRequest(BaseModel):
    decision: str = Field(pattern=r"^(approve|reject|revise)$")
    comment: str | None = Field(default=None, max_length=2000)


def _safe_state(run: AgentRun) -> dict[str, object]:
    state = dict(run.state_json)
    state.pop("input", None)
    return state


def _run_out(run: AgentRun) -> dict[str, object]:
    return {
        "run_id": str(run.id), "thread_id": run.thread_id,
        "status": run.status.value, "current_agent": run.current_node,
        "revision": run.revision, "state": _safe_state(run),
        "error_code": run.error_code,
    }


@router.post("", status_code=201)
async def start_agent_run(
    body: CreateAgentRunRequest,
    tenant: TenantContext = Depends(require_tenant_roles(Role.ANALYST, Role.MANAGER, Role.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    if body.project_id is not None:
        project = await session.scalar(
            select(Project).where(
                Project.id == body.project_id,
                Project.organization_id == tenant.organization.id,
            )
        )
        if project is None:
            raise APIError(404, "project_not_found", "Project was not found")
    run = await create_run(
        session, organization_id=tenant.organization.id, project_id=body.project_id,
        input_data=body.input,
    )
    # Execution is durable after every node. A queue worker can call the same
    # function later; the API path keeps local and test deployments useful.
    await execute_run(session, run, settings)
    return _run_out(run)


@router.get("/{run_id}")
async def get_agent_run(
    run_id: UUID,
    tenant: TenantContext = Depends(require_tenant_roles(Role.VIEWER, Role.ANALYST, Role.MANAGER, Role.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    run = await session.scalar(select(AgentRun).where(AgentRun.id == run_id, AgentRun.organization_id == tenant.organization.id))
    if run is None:
        raise APIError(404, "agent_run_not_found", "Agent run was not found")
    return _run_out(run)


@router.post("/{run_id}/approval")
async def approve_agent_run(
    run_id: UUID,
    body: ApprovalRequest,
    tenant: TenantContext = Depends(require_tenant_roles(Role.MANAGER, Role.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    run = await session.scalar(select(AgentRun).where(AgentRun.id == run_id))
    if run is None:
        raise APIError(404, "agent_run_not_found", "Agent run was not found")
    approval = await decide_run(
        session, run, organization_id=tenant.organization.id,
        reviewer_user_id=tenant.user.id, reviewer_role=tenant.membership.role,
        decision=body.decision, comment=body.comment,
    )
    # Revision requests re-enter the same governed graph from its durable
    # checkpoint. Approval is finalized only after this explicit transition,
    # keeping rejected/revised runs from being reported as completed.
    if body.decision == "revise":
        await execute_run(session, run, settings)
    elif body.decision == "approve":
        await finalize_approved_run(session, run)
    return {"run_id": str(run.id), "decision": approval.decision, "status": run.status.value, "revision": approval.revision}


@router.get("/{run_id}/events")
async def agent_events(
    run_id: UUID,
    after: int = Query(default=0, ge=0),
    tenant: TenantContext = Depends(require_tenant_roles(Role.VIEWER, Role.ANALYST, Role.MANAGER, Role.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> StreamingResponse:
    run = await session.scalar(select(AgentRun).where(AgentRun.id == run_id, AgentRun.organization_id == tenant.organization.id))
    if run is None:
        raise APIError(404, "agent_run_not_found", "Agent run was not found")

    async def body() -> AsyncIterator[str]:
        async for event in stream_events(session, run, after):
            payload = {"sequence": event.sequence, "event": event.event_type, "node": event.node, "summary": event.safe_summary, "payload": event.payload_json}
            yield f"id: {event.sequence}\nevent: {event.event_type}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"
        yield "event: stream.end\ndata: {}\n\n"

    return StreamingResponse(body(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
