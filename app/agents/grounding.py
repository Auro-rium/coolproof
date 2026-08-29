"""Tenant-scoped, non-text grounding for governed agent runs.

Agents receive references to durable domain facts, never the request payload,
document chunks, provider envelopes, or model completions.  This module keeps
that boundary in one place so every provider (including a future LLM provider)
gets the same safe context.
"""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import HeatAnalysis, HeatAnalysisStatus, Project
from app.db.phase3_models import (
    Document,
    DocumentChunk,
    Intervention,
    InterventionEvidence,
    PortfolioRun,
)


class GroundingError(ValueError):
    """A requested persisted reference is absent from the active tenant."""


_HEAT_FACT_KEYS = (
    "mean_temperature_c",
    "threshold_c",
    "persistence_hours",
    "exposure_hours",
    "threshold_exceedance_c",
    "exposure_score",
    "population",
    "criticality",
    "method",
)
_PORTFOLIO_FACT_KEYS = (
    "total_cost",
    "total_benefit",
    "total_uncertainty",
    "remaining_budget",
    "status",
)


def _uuid(value: object, reference: str) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise GroundingError(f"invalid_{reference}_reference") from exc


def _one_or_many(value: object) -> list[object]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _references(input_data: dict[str, object]) -> dict[str, list[object]]:
    nested = input_data.get("references")
    source = nested if isinstance(nested, dict) else input_data

    def pick(*names: str) -> list[object]:
        for name in names:
            if name in source:
                return _one_or_many(source[name])
        return []

    return {
        "heat": pick("heat_analysis_id", "heat_analysis_ids", "heat_id"),
        "portfolio": pick("portfolio_run_id", "portfolio_run_ids", "portfolio_id"),
        "intervention": pick(
            "intervention_id", "intervention_ids", "interventions"
        ),
    }


def safe_input_references(input_data: dict[str, object]) -> dict[str, object]:
    """Persist only UUID references needed to resolve durable grounding.

    Invalid values are intentionally dropped here; ``resolve_grounding``
    still rejects an explicitly supplied invalid reference before execution.
    This prevents arbitrary prompts/source text from entering ``AgentRun``.
    """
    safe: dict[str, list[str]] = {}
    names = {
        "heat": "heat_analysis_ids",
        "portfolio": "portfolio_run_ids",
        "intervention": "intervention_ids",
    }
    for kind, values in _references(input_data).items():
        valid: list[str] = []
        for value in values:
            try:
                valid.append(str(_uuid(value, kind)))
            except GroundingError:
                continue
        if valid:
            safe[names[kind]] = valid
    return {"references": safe} if safe else {}


def _safe_numeric_facts(payload: object, keys: tuple[str, ...]) -> dict[str, object]:
    """Copy only known scalar domain facts, excluding arbitrary provider text."""
    if not isinstance(payload, dict):
        return {}
    result: dict[str, object] = {}
    for key in keys:
        value = payload.get(key)
        if isinstance(value, (bool, int, float)) and not isinstance(value, complex):
            result[key] = value
        elif key in {"method", "status"} and isinstance(value, str):
            result[key] = value[:120]
    return result


def _safe_filename(value: str) -> str:
    # A filename is metadata used to identify a citation, not source text.
    return value.rsplit("/", 1)[-1].replace("\n", " ")[:160]


async def _resolve_project(
    session: AsyncSession, organization_id: UUID, project_id: UUID | None
) -> tuple[Project | None, dict[str, object] | None]:
    if project_id is None:
        return None, None
    project = await session.scalar(
        select(Project).where(
            Project.id == project_id, Project.organization_id == organization_id
        )
    )
    if project is None:
        raise GroundingError("project_reference_not_found")
    return project, {"project_id": str(project.id), "name": project.name[:200]}


async def _resolve_heat(
    session: AsyncSession,
    organization_id: UUID,
    project_id: UUID | None,
    references: list[object],
) -> dict[str, object] | None:
    heat_id = _uuid(references[0], "heat_analysis") if references else None
    statement = select(HeatAnalysis).where(HeatAnalysis.organization_id == organization_id)
    if heat_id is not None:
        statement = statement.where(HeatAnalysis.id == heat_id)
    elif project_id is not None:
        statement = statement.where(HeatAnalysis.project_id == project_id)
    statement = statement.order_by(HeatAnalysis.created_at.desc())
    analysis = await session.scalar(statement)
    if analysis is None:
        if heat_id is not None:
            raise GroundingError("heat_analysis_reference_not_found")
        return None
    if project_id is not None and analysis.project_id != project_id:
        raise GroundingError("heat_analysis_project_mismatch")
    result = analysis.result if analysis.status == HeatAnalysisStatus.SUCCEEDED else None
    expires = analysis.expires_at
    stale = bool(expires is not None and expires < datetime.now(UTC))
    citation = f"heat:{analysis.id}"
    return {
        "analysis_id": str(analysis.id),
        "project_id": str(analysis.project_id),
        "zone_id": str(analysis.zone_id),
        "status": analysis.status.value,
        "stale": stale,
        "source_updated_at": analysis.source_updated_at.isoformat()
        if analysis.source_updated_at
        else None,
        "facts": _safe_numeric_facts(result, _HEAT_FACT_KEYS),
        "citation": citation,
    }


async def _resolve_portfolio(
    session: AsyncSession,
    organization_id: UUID,
    project_id: UUID | None,
    references: list[object],
) -> dict[str, object] | None:
    portfolio_id = _uuid(references[0], "portfolio_run") if references else None
    statement = select(PortfolioRun).where(PortfolioRun.organization_id == organization_id)
    if portfolio_id is not None:
        statement = statement.where(PortfolioRun.id == portfolio_id)
    elif project_id is not None:
        statement = statement.where(PortfolioRun.project_id == project_id)
    statement = statement.order_by(PortfolioRun.created_at.desc())
    portfolio = await session.scalar(statement)
    if portfolio is None:
        if portfolio_id is not None:
            raise GroundingError("portfolio_run_reference_not_found")
        return None
    if project_id is not None and portfolio.project_id not in {None, project_id}:
        raise GroundingError("portfolio_run_project_mismatch")
    result = portfolio.result_json if isinstance(portfolio.result_json, dict) else {}
    allocations = result.get("allocations")
    safe_allocations: list[dict[str, object]] = []
    if isinstance(allocations, list):
        for item in allocations:
            if not isinstance(item, dict):
                continue
            safe: dict[str, object] = {}
            for key in ("zone_id", "intervention_id"):
                value = item.get(key)
                if isinstance(value, (str, int)):
                    safe[key] = str(value)[:120]
            for key in ("units", "cost", "benefit", "uncertainty"):
                value = item.get(key)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    safe[key] = value
            if safe:
                safe_allocations.append(safe)
    return {
        "portfolio_run_id": str(portfolio.id),
        "project_id": str(portfolio.project_id) if portfolio.project_id else None,
        "budget": portfolio.budget,
        "facts": _safe_numeric_facts(result, _PORTFOLIO_FACT_KEYS),
        "allocation_count": len(safe_allocations),
        "allocations": safe_allocations,
        "citation": f"portfolio:{portfolio.id}",
    }


async def _resolve_interventions(
    session: AsyncSession,
    organization_id: UUID,
    references: list[object],
) -> list[dict[str, object]]:
    ids = [_uuid(item, "intervention") for item in references]
    statement = select(Intervention).where(
        Intervention.organization_id == organization_id, Intervention.active.is_(True)
    )
    if ids:
        statement = statement.where(Intervention.id.in_(ids))
    interventions = (await session.scalars(statement.order_by(Intervention.name))).all()
    if ids and {item.id for item in interventions} != set(ids):
        raise GroundingError("intervention_reference_not_found")

    output: list[dict[str, object]] = []
    for intervention in interventions:
        evidence_rows = (
            await session.execute(
                select(InterventionEvidence, Document, DocumentChunk)
                .join(Document, Document.id == InterventionEvidence.document_id)
                .join(DocumentChunk, DocumentChunk.id == InterventionEvidence.chunk_id)
                .where(
                    InterventionEvidence.organization_id == organization_id,
                    InterventionEvidence.intervention_id == intervention.id,
                    Document.organization_id == organization_id,
                    DocumentChunk.organization_id == organization_id,
                )
                .order_by(InterventionEvidence.created_at)
            )
        ).all()
        citations: list[dict[str, object]] = []
        for evidence, document, chunk in evidence_rows:
            citation: dict[str, object] = {
                "evidence_id": str(evidence.id),
                "document_id": str(document.id),
                "chunk_id": str(chunk.id),
                "filename": _safe_filename(document.filename),
                "page_number": chunk.page_number,
                "source_label": (evidence.source_label or "")[:160] or None,
                "citation": f"evidence:{evidence.id}",
            }
            citations.append(citation)
        output.append(
            {
                "intervention_id": str(intervention.id),
                "name": intervention.name[:180],
                "category": intervention.category[:80],
                "unit_cost": intervention.unit_cost,
                "cooling_score": intervention.cooling_score,
                "evidence_count": len(citations),
                "citations": citations,
            }
        )
    return output


async def resolve_grounding(
    session: AsyncSession,
    *,
    organization_id: UUID,
    project_id: UUID | None,
    input_data: dict[str, object],
) -> dict[str, object]:
    """Resolve requested/latest tenant-owned facts into a safe agent context.

    Only IDs, bounded metadata, and deterministic numeric fields are returned.
    In particular, document claims/chunks and arbitrary request fields never
    cross into the provider context or durable agent state.
    """
    project, project_summary = await _resolve_project(
        session, organization_id, project_id
    )
    del project
    refs = _references(input_data)
    heat = await _resolve_heat(session, organization_id, project_id, refs["heat"])
    portfolio = await _resolve_portfolio(
        session, organization_id, project_id, refs["portfolio"]
    )
    interventions = await _resolve_interventions(
        session, organization_id, refs["intervention"]
    )

    citations: list[str] = []
    if heat:
        citations.append(str(heat["citation"]))
    if portfolio:
        citations.append(str(portfolio["citation"]))
    for intervention in interventions:
        citation_rows = intervention.get("citations")
        if isinstance(citation_rows, list):
            for citation in citation_rows:
                if isinstance(citation, dict) and isinstance(citation.get("citation"), str):
                    citations.append(citation["citation"])
    return {
        "resolved": True,
        "project": project_summary,
        "heat": heat,
        "interventions": interventions,
        "portfolio": portfolio,
        "citations": citations,
    }


def grounded_citations(grounding: dict[str, object]) -> set[str]:
    """Return only citation IDs produced by the resolver."""
    values = grounding.get("citations")
    return {item for item in values if isinstance(item, str)} if isinstance(values, list) else set()


def summary_for_agent(name: str, grounding: dict[str, object]) -> str:
    """Produce a bounded factual status line without copying provider output."""
    heat = grounding.get("heat")
    portfolio = grounding.get("portfolio")
    interventions = grounding.get("interventions")
    if name == "heat_intelligence":
        detail = heat.get("status", "unavailable") if isinstance(heat, dict) else "unavailable"
        return f"Heat Intelligence reviewed persisted heat evidence ({detail})."
    if name == "intervention_analyst":
        count = len(interventions) if isinstance(interventions, list) else 0
        return f"Intervention Analyst reviewed {count} tenant-scoped catalogue entries."
    if name == "portfolio":
        count = portfolio.get("allocation_count", 0) if isinstance(portfolio, dict) else 0
        return f"Portfolio reviewed the persisted deterministic result ({count} allocations)."
    return "Verification reviewed the persisted governed workflow inputs."


def safe_provider_facts(facts: dict[str, object]) -> dict[str, object]:
    """Keep provider facts to scalar, non-text measurements only."""
    safe: dict[str, object] = {}
    for key, value in facts.items():
        if key.endswith("_id") and isinstance(value, (str, UUID)):
            safe[key] = str(value)[:120]
        elif key in {
            "exposure_score", "mean_temperature_c", "threshold_c", "persistence_hours",
            "threshold_exceedance_c", "total_cost", "total_benefit", "total_uncertainty",
            "remaining_budget", "confidence", "allocation_count", "evidence_count",
        } and isinstance(value, (int, float)) and not isinstance(value, bool):
            safe[key] = value
        elif key in {"status", "method", "agent"} and isinstance(value, str):
            safe[key] = value[:120]
    return safe
