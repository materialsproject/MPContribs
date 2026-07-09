from unittest.mock import AsyncMock, MagicMock

import pytest
from botocore.exceptions import ClientError
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mpcontribs_api.dependencies import get_db, get_s3
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


def _make_s3(head_ok: bool) -> MagicMock:
    """Build a mock S3 client whose head_bucket is awaitable."""
    s3 = MagicMock(name="s3")
    if head_ok:
        s3.head_bucket = AsyncMock(return_value={})
    else:
        s3.head_bucket = AsyncMock(
            side_effect=ClientError({"Error": {"Code": "503", "Message": "s3 down"}}, "HeadBucket")
        )
    return s3


@pytest.fixture
def health_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(healthcheck_router, prefix="/healthcheck")
    return app


def _client(app: FastAPI, db: MagicMock, s3: MagicMock | None = None) -> TestClient:
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_s3] = lambda: s3 if s3 is not None else _make_s3(head_ok=True)
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Healthy path
# ---------------------------------------------------------------------------


class TestHealthcheckHealthy:
    def test_returns_200(self, health_app):
        r = _client(health_app, _make_db(ping_ok=True), _make_s3(head_ok=True)).get("/healthcheck")
        assert r.status_code == 200

    def test_body_reports_healthy(self, health_app):
        r = _client(health_app, _make_db(ping_ok=True), _make_s3(head_ok=True)).get("/healthcheck")
        assert r.json() == {"version": "0.0.0-test", "status": "healthy", "mongo": "ok", "s3": "ok"}

    def test_pings_mongo(self, health_app):
        db = _make_db(ping_ok=True)
        _client(health_app, db, _make_s3(head_ok=True)).get("/healthcheck")
        db.client.admin.command.assert_awaited_once_with("ping")

    def test_probes_s3(self, health_app):
        s3 = _make_s3(head_ok=True)
        _client(health_app, _make_db(ping_ok=True), s3).get("/healthcheck")
        s3.head_bucket.assert_awaited_once()


# ---------------------------------------------------------------------------
# Unhealthy path (Mongo unreachable)
# ---------------------------------------------------------------------------


class TestHealthcheckMongoUnhealthy:
    def test_returns_503(self, health_app):
        r = _client(health_app, _make_db(ping_ok=False)).get("/healthcheck")
        assert r.status_code == 503

    def test_body_reports_unreachable(self, health_app):
        # The StarletteHTTPException handler reshapes the response into the
        # standard error envelope, stringifying the detail dict into `message`.
        r = _client(health_app, _make_db(ping_ok=False)).get("/healthcheck")
        message = r.json()["error"]["message"]
        assert "unhealthy" in message
        assert "unreachable" in message

    def test_ping_failure_does_not_leak_exception_text(self, health_app):
        # The raised HTTPException carries a controlled detail dict, not the
        # underlying "mongo down" ConnectionError message.
        r = _client(health_app, _make_db(ping_ok=False)).get("/healthcheck")
        assert "mongo down" not in r.text

    def test_s3_not_probed_when_mongo_down(self, health_app):
        # Mongo is checked first; a failure short-circuits before S3 is touched.
        s3 = _make_s3(head_ok=True)
        _client(health_app, _make_db(ping_ok=False), s3).get("/healthcheck")
        s3.head_bucket.assert_not_awaited()


# ---------------------------------------------------------------------------
# Unhealthy path (S3 unreachable)
# ---------------------------------------------------------------------------


class TestHealthcheckS3Unhealthy:
    def test_returns_503(self, health_app):
        r = _client(health_app, _make_db(ping_ok=True), _make_s3(head_ok=False)).get("/healthcheck")
        assert r.status_code == 503

    def test_body_reports_unreachable(self, health_app):
        r = _client(health_app, _make_db(ping_ok=True), _make_s3(head_ok=False)).get("/healthcheck")
        message = r.json()["error"]["message"]
        assert "unhealthy" in message
        assert "unreachable" in message

    def test_s3_failure_does_not_leak_exception_text(self, health_app):
        # The controlled detail dict is returned, not the underlying boto error text.
        r = _client(health_app, _make_db(ping_ok=True), _make_s3(head_ok=False)).get("/healthcheck")
        assert "s3 down" not in r.text
