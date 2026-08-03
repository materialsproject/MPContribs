"""Tests for the legacy-compatibility redirect/deprecation router.

The legacy (Flask) API lived at the service root (e.g. ``/contributions/``);
the rewrite serves everything under ``/api/v1``. The redirects router mounted
at the root either 308-redirects to the new location (preserving method, body
and query string) or returns ``410 Gone`` for endpoints with no counterpart.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.integration.conftest import make_test_app

# 308 keeps the method/body intact; assert it explicitly so a future change to
# 301/302 (which downgrade POST/PUT to GET) is caught.
PERMANENT_REDIRECT = 308
GONE = 410


@pytest.fixture(scope="module")
def app() -> FastAPI:
    return make_test_app()


@pytest.fixture
def client(app: FastAPI):
    """Client that does NOT auto-follow redirects, so we can assert on 3xx."""
    with TestClient(app, raise_server_exceptions=False, follow_redirects=False) as c:
        yield c


# ---------------------------------------------------------------------------
# Redirects: legacy endpoints with a direct /api/v1 counterpart
# ---------------------------------------------------------------------------

# (method, legacy_path, expected /api/v1 location)
REDIRECT_CASES = [
    # contributions
    ("GET", "/contributions/", "/api/v1/contributions"),
    ("POST", "/contributions/", "/api/v1/contributions"),
    ("PUT", "/contributions/", "/api/v1/contributions"),
    ("DELETE", "/contributions/", "/api/v1/contributions"),
    ("GET", "/contributions/abc123/", "/api/v1/contributions/abc123"),
    ("PUT", "/contributions/abc123/", "/api/v1/contributions/abc123"),
    ("DELETE", "/contributions/abc123/", "/api/v1/contributions/abc123"),
    ("GET", "/contributions/download/gz/", "/api/v1/contributions/download/gz"),
    # projects (GET collection + item verbs)
    ("GET", "/projects/", "/api/v1/projects"),
    ("GET", "/projects/my-proj/", "/api/v1/projects/my-proj"),
    ("PUT", "/projects/my-proj/", "/api/v1/projects/my-proj"),
    ("DELETE", "/projects/my-proj/", "/api/v1/projects/my-proj"),
    # read-only components
    ("GET", "/structures/", "/api/v1/structures"),
    ("GET", "/structures/sid/", "/api/v1/structures/sid"),
    ("GET", "/structures/download/gz/", "/api/v1/structures/download/gz"),
    ("GET", "/tables/", "/api/v1/tables"),
    ("GET", "/tables/tid/", "/api/v1/tables/tid"),
    ("GET", "/tables/download/gz/", "/api/v1/tables/download/gz"),
    ("GET", "/attachments/", "/api/v1/attachments"),
    ("GET", "/attachments/aid/", "/api/v1/attachments/aid"),
    ("GET", "/attachments/download/gz/", "/api/v1/attachments/download/gz"),
]


class TestRedirects:
    @pytest.mark.parametrize("method, legacy_path, new_path", REDIRECT_CASES)
    def test_status_is_permanent_redirect(self, client, method, legacy_path, new_path):
        r = client.request(method, legacy_path)
        assert r.status_code == PERMANENT_REDIRECT

    @pytest.mark.parametrize("method, legacy_path, new_path", REDIRECT_CASES)
    def test_location_points_to_v1(self, client, method, legacy_path, new_path):
        r = client.request(method, legacy_path)
        assert r.headers["location"] == new_path

    def test_query_string_is_preserved(self, client):
        r = client.get("/contributions/?project=foo&_limit=5")
        assert r.headers["location"] == "/api/v1/contributions?project=foo&_limit=5"

    def test_query_string_preserved_on_item(self, client):
        r = client.get("/structures/sid/?_fields=id,label")
        assert r.headers["location"] == "/api/v1/structures/sid?_fields=id,label"

    def test_download_query_preserved(self, client):
        r = client.get("/tables/download/gz/?format=csv")
        assert r.headers["location"] == "/api/v1/tables/download/gz?format=csv"

    def test_no_query_string_has_no_trailing_question_mark(self, client):
        r = client.get("/projects/")
        assert r.headers["location"] == "/api/v1/projects"
        assert "?" not in r.headers["location"]


# ---------------------------------------------------------------------------
# Deprecations: legacy endpoints with no counterpart → 410 Gone
# ---------------------------------------------------------------------------

# (method, legacy_path)
GONE_CASES = [
    # search helpers (Atlas $search) were not ported
    ("GET", "/contributions/search"),
    ("GET", "/projects/search"),
    # project creation has no POST endpoint in the new API
    ("POST", "/projects/"),
    # email-driven application approval links
    ("GET", "/projects/applications/sometoken"),
    ("GET", "/projects/applications/sometoken/approve"),
    ("GET", "/projects/applications/sometoken/deny"),
    # the whole notebooks resource was dropped
    ("GET", "/notebooks/"),
    ("GET", "/notebooks/nbid/"),
    ("GET", "/notebooks/build"),
    ("GET", "/notebooks/result"),
    ("GET", "/notebooks/result/job-1"),
]


class TestDeprecated:
    @pytest.mark.parametrize("method, path", GONE_CASES)
    def test_status_is_gone(self, client, method, path):
        assert client.request(method, path).status_code == GONE

    @pytest.mark.parametrize("method, path", GONE_CASES)
    def test_error_envelope(self, client, method, path):
        body = client.request(method, path).json()
        assert body["error"]["code"] == "endpoint_deprecated"
        assert body["error"]["message"]

    @pytest.mark.parametrize("method, path", GONE_CASES)
    def test_deprecation_header(self, client, method, path):
        assert client.request(method, path).headers["deprecation"] == "true"

    def test_post_projects_points_at_put_replacement(self, client):
        r = client.post("/projects/")
        assert r.status_code == GONE
        body = r.json()
        assert body["error"]["detail"]["replacement"] == "/api/v1/projects/{id}"

    def test_deprecated_responses_are_not_redirects(self, client):
        # A deprecated endpoint must never carry a Location header.
        r = client.get("/notebooks/build")
        assert "location" not in r.headers
