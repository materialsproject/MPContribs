"""Integration tests for the Kong gateway secret verification.

verify_gateway() is applied as an app-level dependency in production. The
gateway_app fixture (from conftest) keeps that dependency active so we can
test enforcement through the full HTTP cycle without a real database.

The correct header value is the plain secret configured in settings
(MPCONTRIBS_KONG__GATEWAY_SECRET=test-gateway-secret, set in the root
conftest.py).  The mock project/contribution repos are also overridden here so
that a passing gateway request reaches a route and returns a non-gateway error.
"""

from unittest.mock import AsyncMock

import pytest

from mpcontribs_api.domains.contributions.dependencies import get_scoped_contributions
from mpcontribs_api.domains.projects.dependencies import get_scoped_projects
from mpcontribs_api.pagination import Page
from tests.integration.conftest import GATEWAY_SECRET


@pytest.fixture(autouse=True)
def _stub_repos(gateway_app):
    """Inject no-op mock repos so gateway-passing requests don't hit Beanie."""
    proj_repo = AsyncMock()
    proj_repo.get_project.return_value = Page(items=[], next_cursor=None)
    contrib_repo = AsyncMock()
    contrib_repo.get_contributions.return_value = Page(items=[], next_cursor=None)

    gateway_app.dependency_overrides[get_scoped_projects] = lambda: proj_repo
    gateway_app.dependency_overrides[get_scoped_contributions] = lambda: contrib_repo
    yield
    gateway_app.dependency_overrides.clear()


class TestGatewayEnforcement:
    def test_missing_header_returns_403(self, gateway_client):
        r = gateway_client.get("/api/v1/projects")
        assert r.status_code == 403

    def test_wrong_secret_returns_403(self, gateway_client):
        r = gateway_client.get("/api/v1/projects", headers={"x-gateway-secret": "wrong-secret"})
        assert r.status_code == 403

    def test_missing_header_error_code(self, gateway_client):
        r = gateway_client.get("/api/v1/projects")
        assert r.json()["error"]["code"] == "gateway_error"

    def test_correct_secret_passes_gateway(self, gateway_client):
        r = gateway_client.get(
            "/api/v1/projects",
            headers={"x-gateway-secret": GATEWAY_SECRET},
        )
        # Request reached the route — not 403
        assert r.status_code != 403

    def test_correct_secret_on_contributions(self, gateway_client):
        r = gateway_client.get(
            "/api/v1/contributions",
            headers={"x-gateway-secret": GATEWAY_SECRET},
        )
        assert r.status_code != 403

    def test_empty_string_secret_returns_403(self, gateway_client):
        r = gateway_client.get("/api/v1/projects", headers={"x-gateway-secret": ""})
        assert r.status_code == 403
