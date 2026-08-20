"""Phase 3 evidence models, isolated from heat-intelligence persistence."""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDTimestampMixin


class DocumentStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"


class Document(UUIDTimestampMixin, Base):
    __tablename__ = "documents"
    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    project_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(120))
    s3_key: Mapped[str] = mapped_column(String(512), unique=True)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[DocumentStatus] = mapped_column(
        SAEnum(DocumentStatus), default=DocumentStatus.PENDING
    )
    metadata_json: Mapped[dict[str, object]] = mapped_column("metadata", JSON, default=dict)


class DocumentChunk(UUIDTimestampMixin, Base):
    __tablename__ = "document_chunks"
    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    document_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    page_number: Mapped[int | None] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    lexical_text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(
        JSON, nullable=True
    )  # PostgreSQL migration uses vector(1536)
    metadata_json: Mapped[dict[str, object]] = mapped_column("metadata", JSON, default=dict)

    __table_args__ = (UniqueConstraint("document_id", "ordinal"),)


class Intervention(UUIDTimestampMixin, Base):
    __tablename__ = "interventions"
    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(180))
    category: Mapped[str] = mapped_column(String(80))
    unit_cost: Mapped[float] = mapped_column(Float)
    cooling_score: Mapped[float] = mapped_column(Float)
    eligible_land_uses: Mapped[list[str]] = mapped_column(JSON, default=list)
    evidence_document_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("documents.id"), nullable=True
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class InterventionEvidence(UUIDTimestampMixin, Base):
    """A durable, tenant-scoped claim backed by an uploaded document chunk.

    Keeping the claim and the source coordinates separate from the document
    text means an agent can cite evidence without copying arbitrary source
    material into prompts or telemetry.
    """

    __tablename__ = "intervention_evidence"
    __table_args__ = (
        UniqueConstraint("organization_id", "intervention_id", "document_id", "chunk_id"),
    )
    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    intervention_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("interventions.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    chunk_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("document_chunks.id", ondelete="CASCADE"), index=True
    )
    claim: Mapped[str] = mapped_column(String(1000))
    source_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[dict[str, object]] = mapped_column("metadata", JSON, default=dict)


class PortfolioRun(UUIDTimestampMixin, Base):
    __tablename__ = "portfolio_runs"
    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    project_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    budget: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(40), default="completed")
    result_json: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
