from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class ErrorEnvelope(BaseModel):
    error: ErrorDetail
    request_id: str | None = None


class APIError(Exception):
    def __init__(
        self, status_code: int, code: str, message: str, details: dict[str, Any] | None = None
    ):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


def error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    body = ErrorEnvelope(
        error=ErrorDetail(code=code, message=message, details=details),
        request_id=getattr(request.state, "request_id", None),
    )
    return JSONResponse(status_code=status_code, content=body.model_dump(exclude_none=True))


async def api_error_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, APIError):
        return error_response(request, 500, "internal_error", "An unexpected error occurred")
    return error_response(request, exc.status_code, exc.code, exc.message, exc.details)
