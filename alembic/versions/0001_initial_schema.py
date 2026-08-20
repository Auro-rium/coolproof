"""Create the initial CoolProof schema.

This first revision deliberately delegates table creation to the canonical
SQLAlchemy metadata. Future changes should use normal Alembic revisions.
"""

from alembic import op

from app.db.base import Base
from app.db import models as _models  # noqa: F401

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
