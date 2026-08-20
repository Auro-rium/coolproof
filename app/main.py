from __future__ import annotations

import logging
import time

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.heat import router as heat_router
from app.api.projects import router as projects_router
from app.api.routes import router
from app.core.config import get_settings
from app.core.errors import APIError, api_error_handler, error_response
from app.core.middleware import RequestIDMiddleware


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url="/docs" if settings.is_development else None,
    )
    application.add_middleware(RequestIDMiddleware)
    application.add_exception_handler(APIError, api_error_handler)

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return error_response(
            request, 422, "validation_error", "Request validation failed", {"issues": exc.errors()}
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
        response = await call_next(request)
        logging.getLogger("coolproof.access").info(
            "request method=%s path=%s status=%s duration_ms=%d request_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            (time.monotonic() - started) * 1000,
            getattr(request.state, "request_id", None),
        )
        return response

    application.include_router(router)
    application.include_router(projects_router)
    application.include_router(heat_router)
    return application


app = create_app()
