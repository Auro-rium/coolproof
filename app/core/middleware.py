from __future__ import annotations

import re
import time
from collections import defaultdict, deque
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        candidate = request.headers.get("X-Request-ID", "")
        request_id = candidate[:64] if re.fullmatch(r"[A-Za-z0-9._:-]{1,64}", candidate) else str(uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class RequestGuardMiddleware(BaseHTTPMiddleware):
    """Bound request bodies and a small process-local safety limiter.

    The edge proxy remains the primary rate limiter in production; this guard
    prevents accidental resource exhaustion when the API is reached directly.
    """

    def __init__(self, app, *, max_bytes: int = 25 * 1024 * 1024, per_minute: int = 120):  # type: ignore[no-untyped-def]
        super().__init__(app)
        self.max_bytes = max_bytes
        self.per_minute = per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > self.max_bytes:
            request_id = getattr(request.state, "request_id", str(uuid4()))
            return JSONResponse(status_code=413, content={"error": {"code": "request_too_large", "message": "Request body exceeds configured limit", "retryable": False, "request_id": request_id}})
        now = time.monotonic()
        key = request.client.host if request.client else "unknown"
        bucket = self._hits[key]
        while bucket and now - bucket[0] >= 60:
            bucket.popleft()
        if len(bucket) >= self.per_minute:
            request_id = getattr(request.state, "request_id", str(uuid4()))
            return JSONResponse(status_code=429, content={"error": {"code": "rate_limited", "message": "Too many requests", "retryable": True, "request_id": request_id}})
        bucket.append(now)
        return await call_next(request)
