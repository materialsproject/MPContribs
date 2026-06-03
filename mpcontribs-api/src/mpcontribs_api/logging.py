import logging
import sys

import structlog
from opentelemetry import trace

from mpcontribs_api.config import Settings


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

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(log_level)

    # Let uvicorn's loggers flow through the root handler instead of their own.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True


def get_logger(name: str | None = None):
    return structlog.get_logger(name)
