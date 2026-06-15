import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mpcontribs_api.exceptions import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
    PermissionError,
    ValidationError,
)
from tests.integration.conftest import AUTHED_HEADERS, make_test_app

# ---------------------------------------------------------------------------
# Helper: mount a /probe route that raises a specific AppError
# ---------------------------------------------------------------------------


def _app_with_probe(exc: Exception) -> FastAPI:
    """Create a test app with a GET /probe route that raises `exc`."""
    app = make_test_app()

    @app.get("/probe")
    async def _probe():
        raise exc

    return app


def _client(app: FastAPI) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Unknown route — Starlette HTTPException(404) → {"error": {"code": "http_error"}}
# ---------------------------------------------------------------------------


class TestUnknownRoute:
    def test_status_404(self, client):
        r = client.get("/no/such/route", headers=AUTHED_HEADERS)
        assert r.status_code == 404

    def test_error_envelope(self, client):
        r = client.get("/no/such/route", headers=AUTHED_HEADERS)
        body = r.json()
        assert "error" in body
        assert body["error"]["code"] == "http_error"
        assert "message" in body["error"]


# ---------------------------------------------------------------------------
# Request body validation — FastAPI RequestValidationError → 422
# ---------------------------------------------------------------------------


class TestRequestValidation:
    def test_missing_required_body_field(self, client):
        # PUT /api/v1/projects/{id} requires a ProjectIn body
        r = client.put(
            "/api/v1/projects/my-proj",
            json={"title": "Missing required fields"},
            headers=AUTHED_HEADERS,
        )
        assert r.status_code == 422

    def test_validation_error_envelope(self, client):
        r = client.put(
            "/api/v1/projects/my-proj",
            json={"title": "Missing required fields"},
            headers=AUTHED_HEADERS,
        )
        body = r.json()
        assert body["error"]["code"] == "validation_error"
        assert "errors" in body["error"]["detail"]

    def test_non_json_body(self, client):
        r = client.put(
            "/api/v1/projects/my-proj",
            content=b"not json at all",
            headers={**AUTHED_HEADERS, "content-type": "application/json"},
        )
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# AppError subclasses — verify status codes and envelope shapes
# ---------------------------------------------------------------------------


class TestNotFoundError:
    def setup_method(self):
        self._app = _app_with_probe(NotFoundError("project 'foo' not found"))
        self._client = _client(self._app)

    def test_status_404(self):
        assert self._client.get("/probe").status_code == 404

    def test_error_code(self):
        assert self._client.get("/probe").json()["error"]["code"] == "not_found"

    def test_message(self):
        assert "foo" in self._client.get("/probe").json()["error"]["message"]


class TestConflictError:
    def setup_method(self):
        self._app = _app_with_probe(ConflictError("duplicate id"))
        self._client = _client(self._app)

    def test_status_409(self):
        assert self._client.get("/probe").status_code == 409

    def test_error_code(self):
        assert self._client.get("/probe").json()["error"]["code"] == "conflict"


class TestValidationErrorHandler:
    def setup_method(self):
        self._app = _app_with_probe(ValidationError("bad field value"))
        self._client = _client(self._app)

    def test_status_422(self):
        assert self._client.get("/probe").status_code == 422

    def test_error_code(self):
        assert self._client.get("/probe").json()["error"]["code"] == "validation_error"


class TestPermissionErrorHandler:
    def setup_method(self):
        self._app = _app_with_probe(PermissionError(required_role="admin"))
        self._client = _client(self._app)

    def test_status_403(self):
        assert self._client.get("/probe").status_code == 403

    def test_error_code(self):
        assert self._client.get("/probe").json()["error"]["code"] == "permission_denied"


class TestAuthenticationErrorHandler:
    def setup_method(self):
        self._app = _app_with_probe(AuthenticationError("login required"))
        self._client = _client(self._app)

    def test_status_401(self):
        assert self._client.get("/probe").status_code == 401

    def test_error_code(self):
        assert self._client.get("/probe").json()["error"]["code"] == "authentication_error"


# ---------------------------------------------------------------------------
# Envelope shape invariants — all error responses share the same top-level key
# ---------------------------------------------------------------------------


class TestEnvelopeShape:
    @pytest.mark.parametrize(
        "exc, expected_status",
        [
            (NotFoundError("x"), 404),
            (ConflictError("x"), 409),
            (ValidationError("x"), 422),
            (PermissionError(), 403),
            (AuthenticationError("x"), 401),
        ],
    )
    def test_always_has_error_key(self, exc, expected_status):
        app = _app_with_probe(exc)
        r = _client(app).get("/probe")
        assert r.status_code == expected_status
        body = r.json()
        assert "error" in body
        assert "code" in body["error"]
        assert "message" in body["error"]
