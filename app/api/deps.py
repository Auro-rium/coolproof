from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CognitoJWTVerifier, TokenClaims
from app.core.config import Settings, get_settings
from app.core.errors import APIError
from app.db.models import Membership, Organization, Role, User
from app.db.session import get_db_session


@dataclass(frozen=True)
class Principal:
    subject: str
    email: str | None
    roles: frozenset[Role]


@dataclass(frozen=True)
class TenantContext:
    organization: Organization
    user: User
    membership: Membership


async def get_principal(
    authorization: Annotated[str | None, Header()] = None,
    x_development_subject: Annotated[str | None, Header()] = None,
    x_development_role: Annotated[str | None, Header()] = None,
    settings: Settings = Depends(get_settings),
) -> Principal:
    if settings.is_development and settings.allow_development_auth and x_development_subject:
        try:
            roles = frozenset(
                Role(value.strip()) for value in (x_development_role or "viewer").split(",")
            )
        except ValueError as exc:
            raise APIError(401, "invalid_development_role", "Development role is invalid") from exc
        return Principal(subject=x_development_subject, email=None, roles=roles)
    if not authorization or not authorization.startswith("Bearer "):
        raise APIError(401, "authentication_required", "A bearer token is required")
    claims: TokenClaims = await CognitoJWTVerifier(settings).verify(
        authorization.removeprefix("Bearer ")
    )
    role_map = {"viewer": Role.VIEWER, "analyst": Role.ANALYST, "manager": Role.MANAGER, "admin": Role.ADMIN}
    return Principal(
        subject=claims.subject,
        email=claims.email,
        roles=frozenset(role_map[item] for item in claims.roles if item in role_map),
    )


def require_roles(*roles: Role) -> Callable[..., Awaitable[Principal]]:
    async def dependency(principal: Principal = Depends(get_principal)) -> Principal:
        if principal.roles and not principal.roles.intersection(roles):
            raise APIError(
                403, "insufficient_role", "The authenticated role cannot perform this action"
            )
        return principal

    return dependency


def require_tenant_roles(*roles: Role) -> Callable[..., Awaitable[TenantContext]]:
    """Authorize role from the tenant membership, never untrusted token claims."""

    async def dependency(tenant: TenantContext = Depends(get_tenant_context)) -> TenantContext:
        if tenant.membership.role not in roles:
            raise APIError(
                403, "insufficient_role", "Your organization role cannot perform this action"
            )
        return tenant

    return dependency


async def get_tenant_context(
    request: Request,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_db_session),
    x_organization_id: Annotated[UUID | None, Header()] = None,
) -> TenantContext:
    if not x_organization_id:
        raise APIError(400, "organization_required", "X-Organization-ID is required")
    result = await session.execute(
        select(Membership, Organization, User)
        .join(Organization, Membership.organization_id == Organization.id)
        .join(User, Membership.user_id == User.id)
        .where(
            Membership.organization_id == x_organization_id,
            User.cognito_subject == principal.subject,
        )
    )
    row = result.one_or_none()
    if not row:
        raise APIError(
            403, "organization_access_denied", "You are not a member of this organization"
        )
    membership, organization, user = row
    if principal.roles and membership.role not in principal.roles:
        # Development authentication may only narrow access, never widen DB membership.
        raise APIError(
            403, "organization_access_denied", "The development role does not match membership"
        )
    request.state.organization_id = str(organization.id)
    return TenantContext(organization=organization, user=user, membership=membership)
