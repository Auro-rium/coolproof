"""Phase 3 evidence models, isolated from heat-intelligence persistence."""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
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
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    source_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    effective_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    document_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    deleted_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)


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


class VerificationRun(UUIDTimestampMixin, Base):
    """Deterministic, tenant-scoped post-intervention verification result."""

    __tablename__ = "verification_runs"
    __table_args__ = (UniqueConstraint("organization_id", "idempotency_key"),)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    portfolio_run_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("portfolio_runs.id", ondelete="SET NULL"), nullable=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="completed", nullable=False)
    result_json: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    report_s3_key: Mapped[str | None] = mapped_column(String(512), nullable=True)


class ProjectIntervention(UUIDTimestampMixin, Base):
    __tablename__ = "project_interventions"
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), index=True)
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("projects.id"), index=True)
    intervention_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("interventions.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(40), default="planned")


class PortfolioAllocation(UUIDTimestampMixin, Base):
    __tablename__ = "portfolio_allocations"
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), index=True)
    portfolio_run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("portfolio_runs.id", ondelete="CASCADE"), index=True)
    zone_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("zones.id"), index=True)
    intervention_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("interventions.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    cost: Mapped[float] = mapped_column(Float, default=0)


class VerificationObservation(UUIDTimestampMixin, Base):
    __tablename__ = "verification_observations"
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), index=True)
    verification_run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("verification_runs.id", ondelete="CASCADE"), index=True)
    zone_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("zones.id"), index=True)
    observed_at: Mapped[str] = mapped_column(String(40), index=True)
    treatment: Mapped[str] = mapped_column(String(20))
    metric: Mapped[str] = mapped_column(String(80))
    value: Mapped[float] = mapped_column(Float)


class Report(UUIDTimestampMixin, Base):
    __tablename__ = "reports"
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), index=True)
    project_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    verification_run_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("verification_runs.id"), nullable=True)
    s3_key: Mapped[str] = mapped_column(String(512), unique=True)
    report_type: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(40), default="ready")


class UpstreamRequest(UUIDTimestampMixin, Base):
    __tablename__ = "upstream_requests"
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), index=True)
    provider: Mapped[str] = mapped_column(String(80), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(40))
    request_hash: Mapped[str] = mapped_column(String(64))
    response_metadata: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
