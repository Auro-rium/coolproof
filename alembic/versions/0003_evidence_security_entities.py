"""Add normalized evidence, observation, allocation and upstream entities."""
import sqlalchemy as sa
from alembic import op
from app.db.base import Base
from app.db import models as _models  # noqa: F401

revision = "0003_evidence_security_entities"
down_revision = "0002_agent_approval_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Metadata includes all tenant-scoped tables.  create_all is safe for
    # existing deployments and keeps SQLite test databases portable.
    Base.metadata.create_all(bind=op.get_bind())
    inspector = sa.inspect(op.get_bind())
    existing = {column["name"] for column in inspector.get_columns("documents")}
    additions = {
        "version": sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        "source_label": sa.Column("source_label", sa.String(255), nullable=True),
        "effective_date": sa.Column("effective_date", sa.String(32), nullable=True),
        "document_type": sa.Column("document_type", sa.String(80), nullable=True),
        "deleted_at": sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    }
    for name, column in additions.items():
        if name not in existing:
            op.add_column("documents", column)
    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        op.execute("ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS embedding_vector vector(1536)")
        op.execute("CREATE INDEX IF NOT EXISTS ix_document_chunks_lexical_text ON document_chunks USING gin (to_tsvector('simple', lexical_text))")
        op.execute("CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding_vector ON document_chunks USING hnsw (embedding_vector vector_cosine_ops)")


def downgrade() -> None:
    # These are additive operational tables; preserve data on downgrade.
    pass
