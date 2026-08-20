"""Allow append-only approval history for revise/approve cycles."""

import sqlalchemy as sa

from alembic import op

revision = "0002_agent_approval_history"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    uniques = inspector.get_unique_constraints("agent_approvals")
    for item in uniques:
        if item.get("name") and item.get("column_names") == ["run_id"]:
            op.drop_constraint(item["name"], "agent_approvals", type_="unique")
    if not any("run_id" in (item.get("column_names") or []) for item in inspector.get_indexes("agent_approvals")):
        op.create_index("ix_agent_approvals_run_id", "agent_approvals", ["run_id"])


def downgrade() -> None:
    # Existing duplicate revision decisions make restoring a unique constraint
    # unsafe; operators must archive history before an intentional downgrade.
    raise RuntimeError("cannot downgrade approval history with multiple decisions")
