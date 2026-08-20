from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import TenantContext, require_tenant_roles
from app.db.models import Role
from app.db.phase3_models import Document, DocumentChunk, Intervention, InterventionEvidence
from app.db.session import get_db_session
from app.services.interventions import InterventionSpec, is_eligible

router = APIRouter(prefix="/api/v1/interventions", tags=["interventions"])


class EligibilityRequest(BaseModel):
    intervention_id: str
    name: str
    unit_cost: float = Field(gt=0)
    cooling_score: float = Field(ge=0)
    eligible_land_uses: list[str] = Field(min_length=1)
    land_use: str


class InterventionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    category: str = Field(min_length=1, max_length=80)
    unit_cost: float = Field(gt=0)
    cooling_score: float = Field(ge=0)
    eligible_land_uses: list[str] = Field(min_length=1)
    evidence_document_id: UUID | None = None


class EvidenceRequest(BaseModel):
    document_id: UUID
    chunk_id: UUID
    claim: str = Field(min_length=1, max_length=1000)
    source_label: str | None = Field(default=None, max_length=255)
    metadata: dict[str, object] = Field(default_factory=dict)


@router.post("/eligibility")
async def eligibility(
    request: EligibilityRequest,
    _: TenantContext = Depends(require_tenant_roles(Role.ANALYST, Role.MANAGER, Role.ADMIN)),
) -> dict[str, bool]:
    spec = InterventionSpec(
        request.intervention_id,
        request.name,
        request.unit_cost,
        request.cooling_score,
        frozenset(request.eligible_land_uses),
    )
    return {"eligible": is_eligible(spec, request.land_use)}


@router.post("", status_code=201)
async def create_intervention(
    request: InterventionRequest,
    tenant: TenantContext = Depends(require_tenant_roles(Role.ANALYST, Role.MANAGER, Role.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    if request.evidence_document_id is not None:
        document = await session.get(Document, request.evidence_document_id)
        if document is None or document.organization_id != tenant.organization.id:
            raise HTTPException(status_code=404, detail="Evidence document not found")
    item = Intervention(organization_id=tenant.organization.id, **request.model_dump())
    session.add(item)
    await session.commit()
    return {"intervention_id": str(item.id), **request.model_dump(mode="json"), "active": True}


@router.get("")
async def list_interventions(
    tenant: TenantContext = Depends(require_tenant_roles(Role.VIEWER, Role.ANALYST, Role.MANAGER, Role.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> list[dict[str, object]]:
    result = await session.execute(
        select(Intervention).where(
            Intervention.organization_id == tenant.organization.id, Intervention.active.is_(True)
        ).order_by(Intervention.name)
    )
    return [
        {"intervention_id": str(item.id), "name": item.name, "category": item.category,
         "unit_cost": item.unit_cost, "cooling_score": item.cooling_score,
         "eligible_land_uses": item.eligible_land_uses, "evidence_document_id": str(item.evidence_document_id) if item.evidence_document_id else None}
        for item in result.scalars().all()
    ]


@router.post("/{intervention_id}/evidence", status_code=201)
async def add_evidence(
    intervention_id: UUID,
    request: EvidenceRequest,
    tenant: TenantContext = Depends(require_tenant_roles(Role.ANALYST, Role.MANAGER, Role.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    """Attach a claim to a persisted chunk, validating all three tenant links."""
    intervention = await session.get(Intervention, intervention_id)
    document = await session.get(Document, request.document_id)
    chunk = await session.get(DocumentChunk, request.chunk_id)
    if (
        intervention is None
        or document is None
        or chunk is None
        or intervention.organization_id != tenant.organization.id
        or document.organization_id != tenant.organization.id
        or chunk.organization_id != tenant.organization.id
        or chunk.document_id != document.id
    ):
        raise HTTPException(status_code=404, detail="Intervention evidence source not found")
    evidence = InterventionEvidence(
        organization_id=tenant.organization.id,
        intervention_id=intervention.id,
        document_id=document.id,
        chunk_id=chunk.id,
        claim=request.claim,
        source_label=request.source_label,
        metadata_json=request.metadata,
    )
    session.add(evidence)
    await session.commit()
    return {
        "evidence_id": str(evidence.id),
        "intervention_id": str(intervention.id),
        "document_id": str(document.id),
        "chunk_id": str(chunk.id),
        "claim": evidence.claim,
        "source_label": evidence.source_label,
    }


@router.get("/{intervention_id}/evidence")
async def list_evidence(
    intervention_id: UUID,
    tenant: TenantContext = Depends(require_tenant_roles(Role.VIEWER, Role.ANALYST, Role.MANAGER, Role.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> list[dict[str, object]]:
    intervention = await session.get(Intervention, intervention_id)
    if intervention is None or intervention.organization_id != tenant.organization.id:
        raise HTTPException(status_code=404, detail="Intervention not found")
    result = await session.execute(
        select(InterventionEvidence, Document, DocumentChunk)
        .join(Document, Document.id == InterventionEvidence.document_id)
        .join(DocumentChunk, DocumentChunk.id == InterventionEvidence.chunk_id)
        .where(
            InterventionEvidence.intervention_id == intervention.id,
            InterventionEvidence.organization_id == tenant.organization.id,
        )
        .order_by(InterventionEvidence.created_at)
    )
    return [
        {
            "evidence_id": str(evidence.id),
            "document_id": str(document.id),
            "chunk_id": str(chunk.id),
            "filename": document.filename,
            "page_number": chunk.page_number,
            "claim": evidence.claim,
            "excerpt": chunk.text,
            "source_label": evidence.source_label,
        }
        for evidence, document, chunk in result.all()
    ]


@router.delete("/{intervention_id}/evidence/{evidence_id}", status_code=204)
async def remove_evidence(
    intervention_id: UUID,
    evidence_id: UUID,
    tenant: TenantContext = Depends(require_tenant_roles(Role.ANALYST, Role.MANAGER, Role.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    evidence = await session.get(InterventionEvidence, evidence_id)
    if (
        evidence is None
        or evidence.intervention_id != intervention_id
        or evidence.organization_id != tenant.organization.id
    ):
        raise HTTPException(status_code=404, detail="Intervention evidence not found")
    await session.delete(evidence)
    await session.commit()
