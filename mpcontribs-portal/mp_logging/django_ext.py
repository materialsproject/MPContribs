"""Request logging context for Django apps.

Add to `MIDDLEWARE` (first, so it covers the other middleware):

```python
MIDDLEWARE = ("mp_logging.django_ext.RequestContextMiddleware", ...)
```

The access log itself comes from gunicorn (`gunicorn.access`); the matched
route reaches it through the WSGI environ (`ENVIRON_ROUTE`).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .context import (
    bind_request_context,
    request_fields,
    reset_request_context,
    update_request_context,
)
from .formatters import ENVIRON_ROUTE


def _route(request: Any) -> str | None:
    """The matched URL pattern, e.g. `projects/<str:name>/` or `^search/?$`.

    Only known after URL resolution, i.e. from `process_view` on.
    """
    match = getattr(request, "resolver_match", None)
    route = getattr(match, "route", None)
    if not route:
        return None
    # Django's patterns have no leading slash; match the request path's form
    return route if route.startswith(("/", "^")) else f"/{route}"


class RequestContextMiddleware:
    """Add the current request's fields to every record logged during it."""

    def __init__(self, get_response: Callable[[Any], Any]) -> None:
        self.get_response = get_response

    def __call__(self, request: Any) -> Any:
        token = bind_request_context(
            request_fields(request.method, request.path, request.headers)
        )
        try:
            return self.get_response(request)
        finally:
            reset_request_context(token)

    def process_view(
        self, request: Any, view_func: Any, view_args: Any, view_kwargs: Any
    ) -> None:
        """Add the matched route, once Django has resolved the URL."""
        route = _route(request)
        if route:
            update_request_context({"http.route": route})
            # request.META is the WSGI environ that gunicorn's access log reads
            request.META[ENVIRON_ROUTE] = route
