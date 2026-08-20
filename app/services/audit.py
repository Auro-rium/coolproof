from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditEvent


async def record_audit_event(
    session: AsyncSession,
    *,
    organization_id: UUID,
    actor_user_id: UUID | None,
    event_type: str,
    resource_type: str,
    resource_id: UUID,
    metadata: dict[str, object] | None = None,
) -> None:
    session.add(
        AuditEvent(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            event_type=event_type,
            resource_type=resource_type,
            resource_id=str(resource_id),
            metadata_json=metadata or {},
            occurred_at=datetime.now(UTC),
        )
    )
