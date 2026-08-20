from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class ErrorDetail(BaseModel):
    code: str
    message: str
    retryable: bool = False
    request_id: str | None = None
    details: dict[str, Any] | None = None


class ErrorEnvelope(BaseModel):
    error: ErrorDetail


class APIError(Exception):
    def __init__(
        self, status_code: int, code: str, message: str,
        details: dict[str, Any] | None = None, retryable: bool | None = None,
    ):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        self.retryable = retryable if retryable is not None else status_code >= 500 or status_code == 429


def error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    retryable: bool | None = None,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    body = ErrorEnvelope(
        error=ErrorDetail(
            code=code,
            message=message,
            retryable=retryable if retryable is not None else status_code >= 500 or status_code == 429,
            request_id=request_id,
            details=details,
        ),
    )
    return JSONResponse(status_code=status_code, content=body.model_dump(exclude_none=True))


async def api_error_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, APIError):
        return error_response(request, 500, "internal_error", "An unexpected error occurred")
    return error_response(request, exc.status_code, exc.code, exc.message, exc.details, exc.retryable)
