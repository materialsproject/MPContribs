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
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from mpcontribs_api.config import Settings
from mpcontribs_api.exceptions import PayloadTooLargeError, error_body
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

# Optional request headers folded into the access log's ``http.*`` block, only when sent.
_ACCESS_LOG_HEADERS: dict[bytes, str] = {
    b"accept": "accept",
    b"accept-language": "accept_language",
    b"accept-encoding": "accept_encoding",
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

        http: dict[str, object] = {
            "method": scope["method"],
            "status_code": status_code,
            "url": url,
            "referer": headers.get(b"referer", b"-").decode("latin-1"),
            "useragent": headers.get(b"user-agent", b"").decode("latin-1"),
            "version": scope.get("http_version", "1.1"),
        }
        for header_name, http_key in _ACCESS_LOG_HEADERS.items():
            value = headers.get(header_name)
            if value is not None:
                http[http_key] = value.decode("latin-1")

        _access_logger.info(
            "http.access",
            http=http,
            network={"bytes_written": bytes_written, "client": {"ip": client_ip}},
            duration=duration_ns,  # Datadog standard `duration` is nanoseconds
            response_time=duration_ns // 1000,  # microseconds, matches the old gunicorn %(D)s
            process=_PROCESS,
        )


class _BodyTooLarge(BaseException):
    """Internal signal that the streamed body exceeded the limit.

    Derives from ``BaseException`` (not ``Exception``) on purpose: FastAPI's request-body parser
    wraps body reads in ``except Exception`` and would otherwise convert our error into a generic
    ``400``. A ``BaseException`` slips past that (and past Starlette's exception middleware) so it
    propagates back to ``BodySizeLimitMiddleware``, which turns it into the uniform ``413``.
    """


class BodySizeLimitMiddleware:
    """Reject request bodies larger than ``max_bytes`` so one caller can't OOM the worker.

    Two enforcement points, because a client can lie about (or omit) ``Content-Length``:

    - **Declared size:** if the ``Content-Length`` header exceeds the limit, respond ``413``
      immediately, before the body is read. This is the common case (the mpcontribs client and
      any ``requests``-based caller set ``Content-Length``) and avoids buffering the upload at all.
    - **Actual size:** otherwise wrap ``receive`` and accumulate the bytes actually delivered
      (chunked transfers, or a lying header); once the running total exceeds the limit, abort. The
      abort is signalled by a ``BaseException`` raised from the wrapped ``receive`` (see
      :class:`_BodyTooLarge` for why) and caught here, so the response is the same uniform ``413``
      as the declared-size path, and the body is never fully buffered.

    Registered inside ``RequestContextMiddleware`` so rejected requests are still access-logged.
    """

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope["headers"])
        declared = self._declared_length(headers.get(b"content-length"))
        if declared is not None and declared > self.max_bytes:
            await self._reject(scope, receive, send)
            return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _BodyTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _BodyTooLarge:
            # Overflow detected mid-body-read: the app hasn't started responding yet, so we own the
            # response and emit the 413 ourselves.
            await self._reject(scope, receive, send)

    @staticmethod
    def _declared_length(raw: bytes | None) -> int | None:
        if raw is None:
            return None
        try:
            return int(raw)
        except ValueError:
            return None

    def _message(self) -> str:
        return f"Request body exceeds the maximum allowed size of {self.max_bytes} bytes."

    async def _reject(self, scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse(
            status_code=PayloadTooLargeError.status_code,
            content=error_body(PayloadTooLargeError.error_code, self._message()),
        )
        await response(scope, receive, send)


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
