import uuid

import structlog
from starlette.types import ASGIApp, Receive, Scope, Send


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        raw_request_id = headers.get(b"x-request-id", b"")
        request_id = raw_request_id.decode() if raw_request_id else str(uuid.uuid4())

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=scope["method"],
            path=scope["path"],
        )
        await self.app(scope, receive, send)
