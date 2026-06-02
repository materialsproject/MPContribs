from __future__ import annotations

from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = structlog.get_logger(__name__)


class AppError(Exception):
    """Base for all application-level domain errors.

    Carries enough structured context for a handler to build an HTTP
    response without the raising code knowing anything about HTTP.
    """

    # Subclasses override these. Kept as class attrs so a handler can read
    # them off the type without instantiating special-casing.
    status_code: int = 500
    error_code: str = "internal_error"  # stable, machine-readable

    def __init__(self, message: str | None = None, **context):
        self.message = message or self.__class__.__name__
        self.context = context  # extra fields for logging / response
        super().__init__(self.message)


class NotFoundError(AppError):
    status_code = 404
    error_code = "not_found"


class ConflictError(AppError):
    status_code = 409
    error_code = "conflict"


class ValidationError(AppError):
    status_code = 422
    error_code = "validation_error"


class PermissionError(AppError):
    status_code = 403
    error_code = "permission_denied"


class AuthenticationError(AppError):
    status_code = 401
    error_code = "authentication_error"


class GatewayError(AppError):
    status_code = 403
    error_code = "gateway_error"


def _error_body(error_code: str, message: str, **public_context) -> dict:
    body: dict[str, Any] = {"error": {"code": error_code, "message": message}}
    if public_context:
        body["error"]["detail"] = public_context
    return body


def register_exception_handlers(app: FastAPI) -> None:
    """Register all exception handlers to the app.

    Args:
        app (FastAPI): the fastapi app to register the exception handlers to
    """

    @app.exception_handler(AppError)
    async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        log = logger.error if exc.status_code >= 500 else logger.info
        log(
            exc.error_code,
            status_code=exc.status_code,
            **exc.context,  # full context to logs
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(
                exc.error_code,
                exc.message,
                # NOTE: not leaking context to client yet
                # - need to make client-safe (no leakage of secrets) on a per-exception type basis
                # **exc.contrxt
            ),
        )

    # Catch-all for anything that isn't an AppError - bugs, unexpected failures.
    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_exception")  # full traceback
        return JSONResponse(
            status_code=500,
            content=_error_body("internal_error", "An unexpected error occurred."),
        )

    # Unify validation errors from pydantic with our exception format
    @app.exception_handler(RequestValidationError)
    async def _handle_validation(request, exc):
        return JSONResponse(
            status_code=422,
            content=_error_body(
                "validation_error", "Request validation failed", errors=exc.errors()
            ),
        )

    # Unify http exceptions from starlette with our exception format
    @app.exception_handler(StarletteHTTPException)
    async def _handle_http(request, exc):
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body("http_error", str(exc.detail)),
        )
