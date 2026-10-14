"""Request logging context for Flask apps."""

from __future__ import annotations

from typing import Any

from flask import Flask, g, request

from .context import (
    bind_request_context,
    request_fields,
    reset_request_context,
)
from .formatters import ENVIRON_ROUTE

_G_KEY = "_mp_logging_token"


def _route() -> str | None:
    """The matched URL rule, e.g. `/projects/<string:name>` (None if unmatched)."""
    rule = request.url_rule
    return rule.rule if rule is not None else None


def init_app(app: Flask) -> None:
    """Add the current request's fields to every record logged during it.

    The access log itself comes from gunicorn (`gunicorn.access`); the matched
    route reaches it through the WSGI environ (`ENVIRON_ROUTE`).
    """

    @app.before_request
    def _bind_logging_context() -> None:
        route = _route()
        if route:
            request.environ[ENVIRON_ROUTE] = route
        token = bind_request_context(
            request_fields(request.method, request.path, request.headers, route=route)
        )
        setattr(g, _G_KEY, token)

    @app.teardown_request
    def _reset_logging_context(exc: Any = None) -> None:
        reset_request_context(g.pop(_G_KEY, None))
