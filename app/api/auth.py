from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import TenantContext, get_tenant_context
from app.core.config import Settings, get_settings

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/config")
@router.get("/api/v1/auth/config")
async def auth_config(settings: Settings = Depends(get_settings)) -> dict[str, object]:
    """Return non-secret information required to render the sign-in contract."""
    return {
        "provider": "cognito",
        "region": settings.cognito_region,
        "user_pool_id": settings.cognito_user_pool_id,
        "configured": bool(settings.resolved_cognito_issuer and settings.cognito_app_client_id),
        "organization_required": True,
    }


@router.get("/session")
@router.get("/api/v1/auth/session")
async def auth_session(tenant: TenantContext = Depends(get_tenant_context)) -> dict[str, object]:
    """Return the authenticated Cognito identity and its tenant membership."""
    return {
        "authenticated": True,
        "user": {"id": str(tenant.user.id), "email": tenant.user.email},
        "organization": {
            "id": str(tenant.organization.id),
            "name": tenant.organization.name,
        },
        "membership": {"role": tenant.membership.role.value},
    }
