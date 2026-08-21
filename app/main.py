from __future__ import annotations

import logging
import time

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.agents import router as agents_router
from app.api.auth import router as auth_router
from app.api.documents import router as documents_router
from app.api.heat import router as heat_router
from app.api.interventions import router as interventions_router
from app.api.optimization import router as optimization_router
from app.api.projects import router as projects_router
from app.api.routes import HTTP_5XX, HTTP_REQUEST_DURATION, HTTP_REQUESTS, router
from app.api.verification import reports_router
from app.api.verification import router as verification_router
from app.core.config import get_settings
from app.core.errors import APIError, api_error_handler, error_response
from app.core.middleware import RequestGuardMiddleware, RequestIDMiddleware
from app.core.tracing import configure_tracing, request_span


def create_app() -> FastAPI:
    settings = get_settings()
    configure_tracing()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        # The hackathon deployment exposes the generated contract for smoke
        # testing; production hardening can gate this behind an operator auth
        # layer without changing the API routes.
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )
    origins = [item.strip() for item in settings.cors_origins.split(",") if item.strip()]
    if origins:
        application.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"], allow_headers=["Authorization", "Content-Type", "X-Organization-ID", "X-Request-ID"])
    application.add_middleware(RequestGuardMiddleware, max_bytes=settings.max_request_bytes, per_minute=settings.rate_limit_per_minute)
    application.add_middleware(RequestIDMiddleware)
    application.add_exception_handler(APIError, api_error_handler)

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Pydantic's raw errors may echo rejected request input. Keep only
        # structural locations and messages in the public contract.
        issues = [
            {"type": issue.get("type"), "loc": issue.get("loc"), "msg": issue.get("msg")}
            for issue in exc.errors()
        ]
        return error_response(
            request, 422, "validation_error", "Request validation failed", {"issues": issues}
        )

    @application.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = "not_found" if exc.status_code == 404 else "http_error"
        return error_response(request, exc.status_code, code, str(exc.detail))

    @application.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logging.getLogger(__name__).exception(
            "Unhandled request error id=%s", getattr(request.state, "request_id", None)
        )
        return error_response(request, 500, "internal_error", "An unexpected error occurred")

    @application.middleware("http")
    async def observe_requests(request: Request, call_next):  # type: ignore[no-untyped-def]
        started = time.monotonic()
        with request_span("http.request", {"http.method": request.method, "http.route": request.url.path}):
            response = await call_next(request)
        logging.getLogger("coolproof.access").info(
            "request method=%s path=%s status=%s duration_ms=%d request_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            (time.monotonic() - started) * 1000,
            getattr(request.state, "request_id", None),
        )
        HTTP_REQUESTS.labels(
            method=request.method, path=request.url.path, status=str(response.status_code)
        ).inc()
        HTTP_REQUEST_DURATION.labels(method=request.method, path=request.url.path).observe(
            time.monotonic() - started
        )
        if response.status_code >= 500:
            HTTP_5XX.labels(method=request.method, path=request.url.path).inc()
        return response

    application.include_router(router)
    application.include_router(auth_router)
    application.include_router(projects_router)
    application.include_router(heat_router)
    application.include_router(documents_router)
    application.include_router(interventions_router)
    application.include_router(optimization_router)
    application.include_router(agents_router)
    application.include_router(verification_router)
    application.include_router(reports_router)
    return application


app = create_app()
