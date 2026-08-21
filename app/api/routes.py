from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Header
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from redis.asyncio import Redis
from sqlalchemy import text
from starlette.responses import Response

from app.api.deps import Principal, get_principal
from app.core.config import Settings, get_settings
from app.core.errors import APIError
from app.db.session import engine

router = APIRouter(tags=["system"])
HTTP_REQUESTS = Counter(
    "coolproof_http_requests_total", "HTTP requests handled", ["method", "path", "status"]
)
HTTP_REQUEST_DURATION = Histogram(
    "coolproof_http_request_duration_seconds", "HTTP request duration", ["method", "path"]
)
HTTP_5XX = Counter("coolproof_http_5xx_total", "HTTP 5xx responses", ["method", "path"])


@router.get("/health/live")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/demo/manifest", tags=["demo"])
@router.get("/api/v1/demo/manifest", tags=["demo"])
async def demo_manifest(settings: Settings = Depends(get_settings)) -> dict[str, object]:
    """Expose the judge-facing workflow without exposing credentials or data."""
    return {
        "product": "CoolProof",
        "positioning": "Agentic urban-cooling investment and verification platform",
        "workflow": [
            {"stage": "heat", "label": "FortyGuard heat evidence", "deterministic": True},
            {"stage": "evidence", "label": "Cited intervention evidence", "deterministic": True},
            {"stage": "optimize", "label": "OR-Tools constrained portfolio", "deterministic": True},
            {"stage": "govern", "label": "Four-agent approval workflow", "deterministic": False},
            {"stage": "verify", "label": "Weather-adjusted matched-control report", "deterministic": True},
        ],
        "architecture": {
            "api": "FastAPI",
            "agent_runtime": "LangGraph",
            "database": "PostgreSQL + pgvector",
            "queue": "Redis",
            "artifacts": "S3",
            "auth": "AWS Cognito JWT",
            "host": "AWS EC2 + Docker Compose",
            "proxy": "Caddy",
            "telemetry": "OpenTelemetry + Prometheus + Grafana",
        },
        "provider": {
            "active": settings.agent_provider,
            "fortyguard_configured": bool(settings.fortyguard_api_key),
            "nim_configured": bool(settings.nim_api_key),
            "backboard_configured": bool(settings.backboard_api_key),
        },
        "evidence_boundary": "Agents orchestrate and explain; deterministic services calculate measurements and allocations.",
    }


@router.get("/health/ready")
async def readiness(settings: Settings = Depends(get_settings)) -> dict[str, str]:
    # Local/test runs intentionally work without managed dependencies. Production
    # readiness must prove that the database and queue are reachable before Caddy
    # sends traffic to the API. Keep failures generic so connection details do
    # not leak through a public health endpoint.
    if settings.is_development:
        return {"status": "healthy", "environment": settings.environment}

    checks: list[str] = []
    try:
        async with asyncio.timeout(3):
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - readiness must never expose driver errors
        checks.append("database")

    if settings.redis_url:
        redis: Redis[bytes] | None = None
        try:
            async with asyncio.timeout(3):
                redis = Redis.from_url(settings.redis_url)
                await redis.ping()
        except Exception:  # noqa: BLE001 - do not expose endpoint/auth details
            checks.append("queue")
        finally:
            if redis is not None:
                await redis.close()
    else:
        checks.append("queue")

    if checks:
        raise APIError(503, "dependencies_unready", "Required dependencies are unavailable")
    return {"status": "healthy", "environment": settings.environment}


@router.get("/metrics", include_in_schema=False)
async def metrics(
    x_metrics_token: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> Response:
    configured_token = settings.metrics_token.get_secret_value() if settings.metrics_token else None
    if configured_token and x_metrics_token != configured_token:
        raise APIError(401, "metrics_authentication_required", "Metrics token is required")
    # The exposition contains only aggregate counters/histograms and is safe
    # for the hackathon's private service network. If an operator configures a
    # token, the check above protects the endpoint without changing the format.
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@router.get("/me")
@router.get("/api/v1/me")
async def me(principal: Principal = Depends(get_principal)) -> dict[str, object]:
    return {
        "subject": principal.subject,
        "email": principal.email,
        "roles": sorted(role.value for role in principal.roles),
    }
