from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import TYPE_CHECKING

import structlog
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.pymongo import PymongoInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from starlette.types import ASGIApp, Receive, Scope, Send

from mpcontribs_api.config import Settings
from mpcontribs_api.logging import build_resource

if TYPE_CHECKING:
    from fastapi import FastAPI

# Guards repeated configure_tracing() (tests, reloads) from re-registering providers or
# double-instrumenting pymongo.
_configured = False

# Lowercased ASGI byte header name -> structlog context key.
_LOGGED_HEADERS: dict[bytes, str] = {
    b"user-agent": "user_agent",
    b"accept": "accept",
    b"accept-language": "accept_language",
    b"accept-encoding": "accept_encoding",
    b"referer": "referer",
    b"content-type": "content_type",
    b"content-length": "content_length",
}


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        raw_headers: Iterable[tuple[bytes, bytes]] = scope["headers"]
        headers = {name: value for name, value in raw_headers}

        raw_request_id = headers.get(b"x-request-id")
        request_id = raw_request_id.decode() if raw_request_id else str(uuid.uuid4())

        context: dict[str, str] = {
            "request_id": request_id,
            "method": scope["method"],
            "path": scope["path"],
        }
        # Kong-resolved consumer identity for log correlation
        raw_consumer_id = headers.get(b"x-consumer-id")
        if raw_consumer_id is not None:
            context["consumer_id"] = raw_consumer_id.decode()
        for header_name, log_key in _LOGGED_HEADERS.items():
            value = headers.get(header_name)
            if value is not None:
                context[log_key] = value.decode("latin-1")

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(**context)

        await self.app(scope, receive, send)


def configure_tracing(settings: Settings) -> None:
    """Register the global tracer and meter providers, exporting via OTLP/gRPC to the collector.

    Covers the request-scoped signals: ``instrument_app`` (below) emits server spans and
    ``http.server`` metrics through these providers, and pymongo spans cover the DB layer. No-op when
    telemetry is disabled or already configured.
    """
    global _configured
    if _configured or not settings.otel.enabled:
        return

    resource = build_resource(settings)
    endpoint = settings.otel.otlp_endpoint
    insecure = settings.otel.insecure

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=insecure)))
    trace.set_tracer_provider(tracer_provider)

    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=endpoint, insecure=insecure),
        export_interval_millis=settings.otel.metric_export_interval_ms,
    )
    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[metric_reader]))

    # Registers a pymongo command listener, so DB spans cover the async client used by Beanie too.
    PymongoInstrumentor().instrument()

    _configured = True


def instrument_app(app: FastAPI, settings: Settings) -> None:
    """Instrument the FastAPI app for server-side request spans/metrics. No-op when disabled."""
    if not settings.otel.enabled:
        return
    # Imported lazily: pulls in the ASGI instrumentation, only needed when enabled.
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app)
