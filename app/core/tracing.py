"""Optional OpenTelemetry tracing with safe structural attributes only."""
from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

try:  # The API remains usable when telemetry packages are intentionally absent.
    from opentelemetry import trace  # type: ignore[import-not-found]
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (  # type: ignore[import-not-found]
        OTLPSpanExporter,
    )
    from opentelemetry.sdk.resources import Resource  # type: ignore[import-not-found]
    from opentelemetry.sdk.trace import TracerProvider  # type: ignore[import-not-found]
    from opentelemetry.sdk.trace.export import BatchSpanProcessor  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover
    trace = None


def configure_tracing() -> None:
    if trace is None or not os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return
    if not isinstance(trace.get_tracer_provider(), TracerProvider):
        provider = TracerProvider(resource=Resource.create({"service.name": "coolproof-api"}))
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(provider)


@contextmanager
def request_span(name: str, attributes: dict[str, Any]) -> Iterator[Any]:
    if trace is None:
        yield None
        return
    tracer = trace.get_tracer("coolproof")
    with tracer.start_as_current_span(name, attributes=attributes) as span:
        yield span
