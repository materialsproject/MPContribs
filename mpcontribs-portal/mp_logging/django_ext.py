"""Request logging context for Django apps.

Add to `MIDDLEWARE` (first, so it covers the other middleware):

```python
MIDDLEWARE = ("mp_logging.django_ext.RequestContextMiddleware", ...)
```

The access log itself comes from gunicorn (`gunicorn.access`).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .context import (
    bind_request_context,
    request_fields,
    reset_request_context,
)


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
