import os
import time
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
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from mpcontribs_api.config import Settings
from mpcontribs_api.logging import build_resource, get_logger

if TYPE_CHECKING:
    from fastapi import FastAPI

# Guards repeated configure_tracing() (tests, reloads) from re-registering providers or
# double-instrumenting pymongo.
_configured = False

# Dedicated access logger. Emits one structured event per request (see RequestContextMiddleware);
# flows through the same root handlers as everything else (stdout + OTLP when enabled).
_access_logger = get_logger("access")

# Process identity, matching the old gunicorn ``{group}/{process}`` prefix and ``%(p)s`` pid. The
# SUPERVISOR_* vars are absent outside supervisord (dev, tests), so these render null there.
_PROCESS = {
    "name": os.getenv("SUPERVISOR_PROCESS_NAME"),
    "group": os.getenv("SUPERVISOR_GROUP_NAME"),
    "id": os.getpid(),
}

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
    """Bind per-request structlog context and emit one structured access log per HTTP request.

    The two concerns live together because both need the request headers parsed once, and this is
    the outermost app middleware, so it observes the final status code, total response bytes, and
    full request duration. The access event uses Datadog standard attribute names (``http.*``,
    ``network.*``, ``duration`` in nanoseconds) so the existing Datadog log pipeline (URL parser,
    User-Agent parser, status-category, date remapper) regenerates the same enriched surface the old
    gunicorn access logs had.
    """

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

        # Capture the final status and body size by wrapping send; the app may call send many times
        # (streaming/chunked), so body bytes accumulate across http.response.body messages.
        status_code = 0
        bytes_written = 0

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code, bytes_written
            if message["type"] == "http.response.start":
                status_code = message["status"]
            elif message["type"] == "http.response.body":
                bytes_written += len(message.get("body", b""))
            await send(message)

        start = time.perf_counter()
        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            # An exception escaped the app's own handlers (e.g. raised in outer middleware or after
            # the response had started, so the catch-all never ran). Record it as a 500 instead of
            # the sentinel 0 so status-based alerting still fires, then re-raise unchanged.
            if status_code == 0:
                status_code = 500
            raise
        finally:
            self._emit_access_log(scope, headers, status_code, bytes_written, start)

    @staticmethod
    def _emit_access_log(
        scope: Scope,
        headers: dict[bytes, bytes],
        status_code: int,
        bytes_written: int,
        start: float,
    ) -> None:
        duration_ns = int((time.perf_counter() - start) * 1e9)
        query_string = scope.get("query_string", b"").decode("latin-1")
        path = scope["path"]
        url = f"{path}?{query_string}" if query_string else path
        # True client IP behind Kong: first X-Forwarded-For hop if present, else the direct peer (which is Kong itself)
        forwarded_for = headers.get(b"x-forwarded-for", b"").decode("latin-1")
        client = scope.get("client")
        client_ip = forwarded_for.split(",")[0].strip() if forwarded_for else (client[0] if client else "")

        _access_logger.info(
            "http.access",
            http={
                "method": scope["method"],
                "status_code": status_code,
                "url": url,
                "referer": headers.get(b"referer", b"-").decode("latin-1"),
                "useragent": headers.get(b"user-agent", b"").decode("latin-1"),
                "version": scope.get("http_version", "1.1"),
            },
            network={"bytes_written": bytes_written, "client": {"ip": client_ip}},
            duration=duration_ns,  # Datadog standard `duration` is nanoseconds
            response_time=duration_ns // 1000,  # microseconds, matches the old gunicorn %(D)s
            process=_PROCESS,
        )


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
