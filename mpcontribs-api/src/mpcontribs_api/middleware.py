import uuid
from collections.abc import Iterable

import structlog
from starlette.types import ASGIApp, Receive, Scope, Send

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
        for header_name, log_key in _LOGGED_HEADERS.items():
            value = headers.get(header_name)
            if value is not None:
                context[log_key] = value.decode("latin-1")

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(**context)

        await self.app(scope, receive, send)
