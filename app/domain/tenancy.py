from __future__ import annotations

from dataclasses import dataclass

from app.db.models import Role


@dataclass(frozen=True)
class TenantPrincipal:
    """Authenticated subject with an explicitly selected organization context."""

    subject: str
    organization_id: str
    role: Role
    email: str | None = None
    user_id: str | None = None
