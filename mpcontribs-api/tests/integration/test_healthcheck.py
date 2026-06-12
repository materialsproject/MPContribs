"""Integration tests for the /health router.

The healthcheck router is mounted by create_app() at /health, but the shared
make_test_app() fixture only mounts the v1 router. So this module builds its
own minimal app that mounts the healthcheck router and overrides the DbDep
dependency with a mock whose admin.command("ping") can be made to succeed or
fail.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mpcontribs_api.dependencies import get_db
from mpcontribs_api.domains.healthcheck.router import router as healthcheck_router
from mpcontribs_api.exceptions import register_exception_handlers


def _make_db(ping_ok: bool) -> MagicMock:
    """Build a mock AsyncDatabase whose client.admin.command is awaitable."""
    db = MagicMock(name="db")
    if ping_ok:
        db.client.admin.command = AsyncMock(return_value={"ok": 1})
    else:
        db.client.admin.command = AsyncMock(side_effect=ConnectionError("mongo down"))
    return db


@pytest.fixture
def health_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(healthcheck_router, prefix="/health")
    return app


def _client(app: FastAPI, db: MagicMock) -> TestClient:
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Healthy path
# ---------------------------------------------------------------------------


class TestHealthcheckHealthy:
    def test_returns_200(self, health_app):
        r = _client(health_app, _make_db(ping_ok=True)).get("/health")
        assert r.status_code == 200

    def test_body_reports_healthy(self, health_app):
        r = _client(health_app, _make_db(ping_ok=True)).get("/health")
        assert r.json() == {"status": "healthy", "mongo": "ok"}

    def test_pings_mongo(self, health_app):
        db = _make_db(ping_ok=True)
        _client(health_app, db).get("/health")
        db.client.admin.command.assert_awaited_once_with("ping")


# ---------------------------------------------------------------------------
# Unhealthy path (DB unreachable)
# ---------------------------------------------------------------------------


class TestHealthcheckUnhealthy:
    def test_returns_503(self, health_app):
        r = _client(health_app, _make_db(ping_ok=False)).get("/health")
        assert r.status_code == 503

    def test_body_reports_unreachable(self, health_app):
        # The StarletteHTTPException handler reshapes the response into the
        # standard error envelope, stringifying the detail dict into `message`.
        r = _client(health_app, _make_db(ping_ok=False)).get("/health")
        message = r.json()["error"]["message"]
        assert "unhealthy" in message
        assert "unreachable" in message

    def test_ping_failure_does_not_leak_exception_text(self, health_app):
        # The raised HTTPException carries a controlled detail dict, not the
        # underlying "mongo down" ConnectionError message.
        r = _client(health_app, _make_db(ping_ok=False)).get("/health")
        assert "mongo down" not in r.text
