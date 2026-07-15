"""Tests for BodySizeLimitMiddleware — the 413 guard against oversized request bodies."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mpcontribs_api.exceptions import register_exception_handlers
from mpcontribs_api.middleware import BodySizeLimitMiddleware

MAX_BYTES = 1024


def _make_app(max_bytes: int = MAX_BYTES) -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=max_bytes)

    @app.post("/echo")
    async def echo(payload: dict) -> dict:
        return {"received": len(payload)}

    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_make_app(), raise_server_exceptions=False)


class TestBodySizeLimit:
    def test_under_limit_passes(self, client: TestClient):
        r = client.post("/echo", json={"a": 1})
        assert r.status_code == 200

    def test_declared_content_length_over_limit_rejected(self, client: TestClient):
        # A body whose Content-Length exceeds the ceiling is rejected before it's read.
        big = {"blob": "x" * (MAX_BYTES * 2)}
        r = client.post("/echo", json=big)
        assert r.status_code == 413
        assert r.json()["error"]["code"] == "payload_too_large"

    def test_streamed_body_over_limit_rejected(self, client: TestClient):
        # No Content-Length (chunked): the middleware accumulates and rejects via raised AppError,
        # which the standard handler renders as a uniform 413.
        def gen():
            yield b"x" * (MAX_BYTES * 2)

        r = client.post("/echo", content=gen())
        assert r.status_code == 413
        assert r.json()["error"]["code"] == "payload_too_large"
