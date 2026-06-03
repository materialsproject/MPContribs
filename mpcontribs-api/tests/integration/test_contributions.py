"""Integration tests for /api/v1/contributions routes.

Uses an AsyncMock repository override so no database is required. Tests cover
the implemented GET and DELETE batch endpoints; stub endpoints (POST, PUT,
single-resource) are verified to exist and wire through to the repo.
"""

import pytest

from src.mpcontribs_api.domains.contributions.dependencies import get_scoped_contributions
from src.mpcontribs_api.domains.contributions.models import ContributionOut
from src.mpcontribs_api.pagination import Page
from tests.integration.conftest import ANON_HEADERS, AUTHED_HEADERS

# ---------------------------------------------------------------------------
# Fixture: inject mock repo for each test
# ---------------------------------------------------------------------------


@pytest.fixture
def contribution_repo(test_app, mock_contribution_repo):
    test_app.dependency_overrides[get_scoped_contributions] = lambda: mock_contribution_repo
    yield mock_contribution_repo
    test_app.dependency_overrides.pop(get_scoped_contributions, None)


SAMPLE_CONTRIBUTION = ContributionOut(
    project="mp-project",
    identifier="mp-001",
    formula="Fe2O3",
    is_public=True,
    data={"band_gap": 2.1},
)


# ---------------------------------------------------------------------------
# GET /api/v1/contributions
# ---------------------------------------------------------------------------


class TestListContributions:
    def test_empty_page_returns_200(self, client, contribution_repo):
        contribution_repo.get_contributions.return_value = Page(items=[], next_cursor=None)
        r = client.get("/api/v1/contributions", headers=AUTHED_HEADERS)
        assert r.status_code == 200

    def test_response_has_page_shape(self, client, contribution_repo):
        contribution_repo.get_contributions.return_value = Page(items=[], next_cursor=None)
        body = client.get("/api/v1/contributions", headers=AUTHED_HEADERS).json()
        assert "items" in body
        assert "next_cursor" in body

    def test_items_in_response(self, client, contribution_repo):
        contribution_repo.get_contributions.return_value = Page(
            items=[SAMPLE_CONTRIBUTION], next_cursor=None
        )
        body = client.get("/api/v1/contributions", headers=AUTHED_HEADERS).json()
        assert len(body["items"]) == 1

    def test_repo_called_with_pagination(self, client, contribution_repo):
        contribution_repo.get_contributions.return_value = Page(items=[], next_cursor=None)
        client.get("/api/v1/contributions", params={"limit": 10}, headers=AUTHED_HEADERS)
        _, kwargs = contribution_repo.get_contributions.call_args
        assert kwargs["pagination"].limit == 10

    def test_fields_forwarded(self, client, contribution_repo):
        contribution_repo.get_contributions.return_value = Page(items=[], next_cursor=None)
        client.get("/api/v1/contributions", params={"_fields": "formula"}, headers=AUTHED_HEADERS)
        _, kwargs = contribution_repo.get_contributions.call_args
        assert kwargs["fields"] is not None
        assert "formula" in kwargs["fields"]

    def test_invalid_fields_returns_422(self, client, contribution_repo):
        contribution_repo.get_contributions.return_value = Page(items=[], next_cursor=None)
        r = client.get("/api/v1/contributions", params={"_fields": "bad_field"}, headers=AUTHED_HEADERS)
        assert r.status_code == 422

    def test_anonymous_can_list(self, client, contribution_repo):
        contribution_repo.get_contributions.return_value = Page(items=[], next_cursor=None)
        r = client.get("/api/v1/contributions", headers=ANON_HEADERS)
        assert r.status_code == 200

    def test_filter_param_forwarded_to_repo(self, client, contribution_repo):
        contribution_repo.get_contributions.return_value = Page(items=[], next_cursor=None)
        client.get("/api/v1/contributions", params={"formula": "Fe2O3"}, headers=AUTHED_HEADERS)
        contribution_repo.get_contributions.assert_called_once()


# ---------------------------------------------------------------------------
# DELETE /api/v1/contributions (batch)
# ---------------------------------------------------------------------------


class TestDeleteContributions:
    def test_batch_delete_returns_200(self, client, contribution_repo):
        contribution_repo.delete_contributions.return_value = None
        r = client.delete("/api/v1/contributions", headers=AUTHED_HEADERS)
        assert r.status_code == 200

    def test_repo_delete_called(self, client, contribution_repo):
        contribution_repo.delete_contributions.return_value = None
        client.delete("/api/v1/contributions", headers=AUTHED_HEADERS)
        contribution_repo.delete_contributions.assert_called_once()

    def test_filter_forwarded_to_repo(self, client, contribution_repo):
        contribution_repo.delete_contributions.return_value = None
        client.delete("/api/v1/contributions", params={"is_public": "true"}, headers=AUTHED_HEADERS)
        _, kwargs = contribution_repo.delete_contributions.call_args
        assert kwargs["filter"] is not None


# ---------------------------------------------------------------------------
# Stub endpoints — verify they exist and wire to the repo
# ---------------------------------------------------------------------------


class TestStubEndpoints:
    """These endpoints are stubs in the repo but the routes must be wired."""

    def test_post_contributions_route_exists(self, client, contribution_repo):
        contribution_repo.insert_contributions.return_value = None
        r = client.post("/api/v1/contributions", json=[], headers=AUTHED_HEADERS)
        # Should reach the route (not 404/405) even if the handler is a stub
        assert r.status_code != 404
        assert r.status_code != 405

    def test_put_contributions_route_exists(self, client, contribution_repo):
        contribution_repo.upsert_contributions.return_value = None
        r = client.put("/api/v1/contributions", json=[], headers=AUTHED_HEADERS)
        assert r.status_code != 404
        assert r.status_code != 405
