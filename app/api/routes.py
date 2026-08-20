from __future__ import annotations

from fastapi import APIRouter, Depends, Header
from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest
from starlette.responses import Response

from app.api.deps import Principal, get_principal
from app.core.config import Settings, get_settings
from app.core.errors import APIError

router = APIRouter(tags=["system"])
HTTP_REQUESTS = Counter(
    "coolproof_http_requests_total", "HTTP requests handled", ["method", "path", "status"]
)


@router.get("/health/live")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness(settings: Settings = Depends(get_settings)) -> dict[str, str]:
    # Deployment startup performs dependency checks; this endpoint remains a cheap
    # probe so it does not consume an RDS connection for every orchestrator poll.
    return {"status": "healthy", "environment": settings.environment}


@router.get("/metrics", include_in_schema=False)
async def metrics(
    x_metrics_token: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> Response:
    configured_token = settings.metrics_token.get_secret_value() if settings.metrics_token else None
    if configured_token and x_metrics_token != configured_token:
        raise APIError(401, "metrics_authentication_required", "Metrics token is required")
    if not configured_token and not settings.is_development:
        raise APIError(503, "metrics_not_configured", "Metrics endpoint is not configured")
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@router.get("/me")
async def me(principal: Principal = Depends(get_principal)) -> dict[str, object]:
    return {
        "subject": principal.subject,
        "email": principal.email,
        "roles": sorted(role.value for role in principal.roles),
    }
