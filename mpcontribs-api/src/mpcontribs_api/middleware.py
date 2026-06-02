import uuid

import structlog


async def bind_request_context(request, call_next):
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        request_id=request.headers.get("x-request-id", str(uuid.uuid4())),
        method=request.method,
        path=request.url.path,
    )
    return await call_next(request)
