"""Small, dependency-light telemetry helpers for the API and workers.

Telemetry is deliberately numeric and structural.  Request bodies, model
prompts/completions, source documents, and credentials must never be emitted.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from prometheus_client import Counter, Histogram

telemetry_events_total = Counter(
    "coolproof_telemetry_events_total", "Operational events", ["event", "status"]
)
verification_runs_total = Counter(
    "coolproof_verification_runs_total", "Verification runs", ["status"]
)
verification_duration_seconds = Histogram(
    "coolproof_verification_duration_seconds", "Verification calculation duration"
)

_SENSITIVE = ("key", "secret", "token", "password", "authorization", "prompt", "completion", "text")


def redact_telemetry(value: Any, *, _key: str = "") -> Any:
    """Return a safe structural representation suitable for logs/metrics.

    Lists and mappings retain shape but sensitive fields are replaced.  Scalar
    source text is never copied; its length is sufficient for operational
    diagnosis.
    """
    key = _key.casefold()
    if any(word in key for word in _SENSITIVE):
        if isinstance(value, (str, bytes)):
            return {"redacted": True, "length": len(value)}
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {str(k): redact_telemetry(v, _key=str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_telemetry(item, _key=key) for item in value]
    return value


def emit_event(event: str, *, status: str = "ok", **fields: Any) -> None:
    """Emit a redacted operational event without payload data."""
    telemetry_events_total.labels(event=event, status=status).inc()
    logging.getLogger("coolproof.telemetry").info(
        "event=%s status=%s fields=%s", event, status, redact_telemetry(fields)
    )
