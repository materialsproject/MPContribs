from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = structlog.get_logger(__name__)


def _record_on_span(exc: Exception) -> None:
    """Attach a server-side exception to the active OTel span so APM error views show the stack.

    No-op when there is no recording span (telemetry disabled or no active span), since the
    sentinel span returned in that case reports ``is_recording() == False``.
    """
    span = trace.get_current_span()
    if span.is_recording():
        span.record_exception(exc)
        span.set_status(Status(StatusCode.ERROR, str(exc)))


class AppError(Exception):
    """Base for all application-level domain errors.

    Carries enough structured context for a handler to build an HTTP
    response without the raising code knowing anything about HTTP.
    """

    # Subclasses override these. Kept as class attrs so a handler can read
    # them off the type without instantiating special-casing.
    status_code: int = 500
    error_code: str = "internal_error"  # stable, machine-readable
    # Optional stdlib log level override. None => the handler derives it from status_code
    # (ERROR for 5xx, INFO for 4xx). Set on a subclass to promote a notable client error,
    # e.g. WARNING for auth failures so they're alertable without logging every 404.
    log_level: int | None = None

    def __init__(self, message: str | None = None, **context):
        self.message = message or self.__class__.__name__
        self.context = context  # extra fields for logging / response
        super().__init__(self.message)


class NotFoundError(AppError):
    status_code = 404
    error_code = "not_found"
    log_level = logging.INFO


class ConflictError(AppError):
    status_code = 409
    error_code = "conflict"
    log_level = logging.INFO


class ValidationError(AppError):
    status_code = 422
    error_code = "validation_error"
    log_level = logging.INFO


class PayloadTooLargeError(AppError):
    status_code = 413
    error_code = "payload_too_large"
    log_level = logging.INFO  # expected client error: caller sent an oversized body


class PermissionError(AppError):
    status_code = 403
    error_code = "permission_denied"
    log_level = logging.WARNING  # security-relevant: alertable, but not a server fault


class AuthenticationError(AppError):
    status_code = 401
    error_code = "authentication_error"
    log_level = logging.WARNING  # security-relevant: alertable, but not a server fault


class DownloadError(AppError):
    status_code = 415
    error_code = "download_error"
    log_level = logging.WARNING


def error_body(error_code: str, message: str, **public_context) -> dict:
    body: dict[str, Any] = {"error": {"code": error_code, "message": message}}
    if public_context:
        body["error"]["detail"] = public_context
    return body


def _sanitize_validation_errors(errors: Sequence[Any]) -> list[dict[str, Any]]:
    """Drop the echoed input value and pydantic doc URL from each error."""
    return [{key: value for key, value in error.items() if key not in ("input", "url")} for error in errors]


def register_exception_handlers(app: FastAPI) -> None:
    """Register all exception handlers to the app.

    Args:
        app (FastAPI): the fastapi app to register the exception handlers to
    """

    @app.exception_handler(AppError)
    async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        is_server_fault = exc.status_code >= 500
        level = exc.log_level if exc.log_level is not None else (logging.ERROR if is_server_fault else logging.INFO)
        if is_server_fault:
            # Only genuine server faults carry a traceback and mark the span; client errors
            # (incl. opt-in WARNING ones like auth failures) are expected and need neither.
            _record_on_span(exc)
            logger.log(level, exc.error_code, status_code=exc.status_code, exc_info=exc, **exc.context)
        else:
            logger.log(level, exc.error_code, status_code=exc.status_code, **exc.context)
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(
                exc.error_code,
                exc.message,
                # NOTE: not leaking context to client yet
                # - need to make client-safe (no leakage of secrets) on a per-exception type basis
                # **exc.context
            ),
        )

    # Catch-all for anything that isn't an AppError - bugs, unexpected failures.
    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        _record_on_span(exc)
        logger.exception("unhandled_exception")  # full traceback
        return JSONResponse(
            status_code=500,
            content=error_body("internal_error", "An unexpected error occurred."),
        )

    # Unify validation errors from pydantic with our exception format
    @app.exception_handler(RequestValidationError)
    async def _handle_validation(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_body(
                "validation_error",
                "Request validation failed",
                errors=jsonable_encoder(_sanitize_validation_errors(exc.errors())),
            ),
        )

    # Unify http exceptions from starlette with our exception format
    @app.exception_handler(StarletteHTTPException)
    async def _handle_http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code >= 500:
            _record_on_span(exc)
            logger.error("http_error", status_code=exc.status_code, exc_info=exc)
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body("http_error", str(exc.detail)),
        )
