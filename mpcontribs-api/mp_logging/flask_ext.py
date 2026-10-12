"""Request logging context for Flask apps."""

from __future__ import annotations

from typing import Any

from flask import Flask, g, request

from .context import (
    bind_request_context,
    request_fields,
    reset_request_context,
)

_G_KEY = "_mp_logging_token"


def init_app(app: Flask) -> None:
    """Add the current request's fields to every record logged during it.

    The access log itself comes from gunicorn (`gunicorn.access`).
    """

    @app.before_request
    def _bind_logging_context() -> None:
        token = bind_request_context(
            request_fields(request.method, request.path, request.headers)
        )
        setattr(g, _G_KEY, token)

    @app.teardown_request
    def _reset_logging_context(exc: Any = None) -> None:
        reset_request_context(g.pop(_G_KEY, None))
