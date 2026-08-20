from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import TenantContext, require_tenant_roles
from app.core.config import Settings, get_settings
from app.core.errors import APIError
from app.db.models import Project, Role
from app.db.phase3_models import Document, DocumentStatus
from app.db.session import get_db_session
from app.retrieval.documents import (
    create_presigned_put_url,
    embed_text,
    finalize_document,
    prepare_upload,
    s3_object_key,
)
from app.retrieval.hybrid import HybridRetriever, RetrievalQuery

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


class CreateDocumentRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(pattern=r"^(application/pdf|text/plain|text/markdown)$")
    project_id: UUID | None = None


class FinalizeDocumentRequest(BaseModel):
    # Optional test/offline path. Production callers upload to S3 first.
    text: str | None = Field(default=None, max_length=25_000_000)


@router.post("/uploads", status_code=201)
async def create_upload(
    request: CreateDocumentRequest,
    tenant: TenantContext = Depends(require_tenant_roles(Role.ANALYST, Role.MANAGER, Role.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    if not settings.documents_bucket:
        raise APIError(503, "document_storage_unavailable", "Document storage is not configured")
    if request.project_id is not None:
        project = await session.scalar(
            select(Project).where(
                Project.id == request.project_id,
                Project.organization_id == tenant.organization.id,
            )
        )
        if project is None:
            raise APIError(404, "project_not_found", "Project was not found")
    document_id = uuid4()
    key = s3_object_key(tenant.organization.id, document_id, request.filename)
    document = Document(
        id=document_id,
        organization_id=tenant.organization.id,
        project_id=request.project_id,
        filename=request.filename,
        content_type=request.content_type,
        s3_key=key,
        sha256="pending",
        status=DocumentStatus.PENDING,
    )
    session.add(document)
    await session.commit()
    return {
        "document_id": str(document_id),
        "object_key": key,
        "upload_url": create_presigned_put_url(
            bucket=settings.documents_bucket, key=key, content_type=request.content_type
        ),
        "status": "pending",
    }


@router.post("/{document_id}/finalize")
async def finalize(
    document_id: UUID,
    request: FinalizeDocumentRequest,
    tenant: TenantContext = Depends(require_tenant_roles(Role.ANALYST, Role.MANAGER, Role.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    document = await session.get(Document, document_id)
    if document is None or document.organization_id != tenant.organization.id:
        raise HTTPException(status_code=404, detail="Document not found")
    content: bytes
    if request.text is not None:
        content = request.text.encode("utf-8")
    else:
        if not settings.documents_bucket:
            raise APIError(503, "document_storage_unavailable", "Document storage is not configured")
        import boto3

        try:
            payload = boto3.client("s3").get_object(Bucket=settings.documents_bucket, Key=document.s3_key)
            content = payload["Body"].read()
        except Exception as exc:
            document.status = DocumentStatus.FAILED
            await session.commit()
            raise APIError(502, "document_fetch_failed", "Unable to retrieve uploaded document") from exc
    try:
        prepare_upload(tenant.organization.id, document.id, document.filename, content, document.content_type)
        count = await finalize_document(session, document, content)
    except ValueError as exc:
        document.status = DocumentStatus.FAILED
        await session.commit()
        raise APIError(422, "document_validation_failed", str(exc)) from exc
    return {"document_id": str(document.id), "status": document.status.value, "chunk_count": count}


@router.get("")
async def list_documents(
    tenant: TenantContext = Depends(require_tenant_roles(Role.VIEWER, Role.ANALYST, Role.MANAGER, Role.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> list[dict[str, object]]:
    """List only documents owned by the selected organization."""
    result = await session.execute(
        select(Document)
        .where(Document.organization_id == tenant.organization.id)
        .order_by(Document.created_at.desc())
    )
    return [
        {
            "document_id": str(item.id),
            "filename": item.filename,
            "content_type": item.content_type,
            "status": item.status.value,
            "project_id": str(item.project_id) if item.project_id else None,
            "sha256": item.sha256 if item.status == DocumentStatus.READY else None,
        }
        for item in result.scalars().all()
    ]


@router.get("/search")
async def search_documents(
    query: str = Query(min_length=1, max_length=1000),
    project_id: UUID | None = None,
    limit: int = Query(default=8, ge=1, le=50),
    tenant: TenantContext = Depends(require_tenant_roles(Role.VIEWER, Role.ANALYST, Role.MANAGER, Role.ADMIN)),
    session: AsyncSession = Depends(get_db_session),
) -> list[dict[str, object]]:
    citations = await HybridRetriever(session).search(
        RetrievalQuery(
            organization_id=tenant.organization.id,
            text=query,
            embedding=tuple(embed_text(query)),
            limit=limit,
            project_id=project_id,
        )
    )
    return [
        {
            "document_id": str(citation.document_id),
            "chunk_id": str(citation.chunk_id),
            "filename": citation.filename,
            "page_number": citation.page_number,
            "excerpt": citation.excerpt,
            "score": citation.score,
        }
        for citation in citations
    ]
