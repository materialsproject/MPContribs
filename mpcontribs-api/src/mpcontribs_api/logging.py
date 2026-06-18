import logging
import sys

import structlog
from opentelemetry import trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource

from mpcontribs_api.config import Settings

# Held across calls so repeated configure_logging() (tests, reloads) reuses one provider rather than
# re-registering. Shared with middleware.py, which builds the tracer/meter providers from the same
# resource so all three signals carry identical service identity.
_logger_provider: LoggerProvider | None = None


def build_resource(settings: Settings) -> Resource:
    """OTEL resource describing this service. Single source of truth for traces, metrics, and logs."""
    return Resource.create(
        {
            "service.name": settings.otel.service_name,
            "service.version": settings.version,
            "deployment.environment": settings.environment,
        }
    )


def add_otel_trace_context(_, __, event_dict):
    span = trace.get_current_span()
    ctx = span.get_span_context()
    # If context is not the sentinel span (ie. we have an active span)
    if ctx.is_valid:
        # Convert to OTel-expected ids
        # ctx ids are formatted as 128-bit (trace_id) and 64-bit (span_id) long numbers.
        # OTel expects them as 0-padded hex numbers
        event_dict["trace_id"] = format(ctx.trace_id, "032x")  # 32 digits
        event_dict["span_id"] = format(ctx.span_id, "016x")  # 16 digits
    return event_dict


def _build_otlp_log_handler(settings: Settings, log_level: int, shared_processors: list) -> LoggingHandler | None:
    """Build a stdlib handler that ships records to the OTLP logs pipeline (the Datadog Agent's OTLP
    receiver), or ``None`` when telemetry is disabled.

    The record body is the structlog event rendered to JSON; the SDK stamps each record with the
    active span's trace/span ids, so logs correlate with traces.
    """
    global _logger_provider
    if not settings.otel.enabled:
        return None

    if _logger_provider is None:
        _logger_provider = LoggerProvider(resource=build_resource(settings))
        _logger_provider.add_log_record_processor(
            BatchLogRecordProcessor(
                OTLPLogExporter(endpoint=settings.otel.otlp_endpoint, insecure=settings.otel.insecure)
            )
        )
        set_logger_provider(_logger_provider)

    handler = LoggingHandler(level=log_level, logger_provider=_logger_provider)
    # ProcessorFormatter renders the event dict to a JSON string, which LoggingHandler uses as the
    # log body (it calls self.format() when a formatter is set). Always JSON regardless of
    # environment - the OTLP body should be structured even when stdout is the dev console renderer.
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.dict_tracebacks,
                structlog.processors.EventRenamer("message"),
                structlog.processors.JSONRenderer(),
            ],
        )
    )
    return handler


def configure_logging(settings: Settings) -> None:
    is_prod = settings.environment == "prod"
    log_level = logging.INFO if is_prod else logging.DEBUG

    # Run on both structlog events and foreign (stdlib) records.
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        add_otel_trace_context,
    ]

    # Exception handling is paired with the renderer, not shared.
    if is_prod:
        render_chain = [
            structlog.processors.dict_tracebacks,
            structlog.processors.EventRenamer("message"),
            structlog.processors.JSONRenderer(),
        ]
    else:
        render_chain = [structlog.dev.ConsoleRenderer()]

    # Handles internal logs emitted by structlog logger
    structlog.configure(
        processors=shared_processors + [structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        cache_logger_on_first_use=True,
    )

    # Handles logs emitted by stdlib logging in external libraries
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            *render_chain,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    # stdout stays for kubectl logs/ebugging; the OTLP handler (when enabled) ships the same
    # records to the collector, so Datadog ingests via OTLP rather than tailing stdout.
    handlers: list[logging.Handler] = [handler]
    otlp_handler = _build_otlp_log_handler(settings, log_level, shared_processors)
    if otlp_handler is not None:
        handlers.append(otlp_handler)

    root = logging.getLogger()
    root.handlers = handlers
    root.setLevel(log_level)

    # Let uvicorn's loggers flow through the root handler instead of their own.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True


def get_logger(name: str | None = None):
    return structlog.get_logger(name)
