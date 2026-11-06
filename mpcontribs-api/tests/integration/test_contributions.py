import pytest

from mpcontribs_api.domains.contributions.dependencies import get_contribution_service
from mpcontribs_api.domains.contributions.models import ContributionOut
from mpcontribs_api.pagination import Page
from tests.integration.conftest import ANON_HEADERS, AUTHED_HEADERS

# ---------------------------------------------------------------------------
# Fixture: inject a mock ContributionService for each test. The routes depend
# only on the service (which owns the repository), so the service is the seam.
# ---------------------------------------------------------------------------


@pytest.fixture
def contribution_service(test_app, mock_contribution_service):
    test_app.dependency_overrides[get_contribution_service] = lambda: mock_contribution_service
    yield mock_contribution_service
    test_app.dependency_overrides.pop(get_contribution_service, None)


SAMPLE_CONTRIBUTION = ContributionOut(
    project="mp-project",
    material_id="mp-001",
    chemical_system_id="Fe-O",
    formula="Fe2O3",
    is_public=True,
    data={"band_gap": 2.1},
)


# ---------------------------------------------------------------------------
# GET /api/v1/contributions
# ---------------------------------------------------------------------------


class TestListContributions:
    def test_empty_page_returns_200(self, client, contribution_service):
        contribution_service.read_many.return_value = Page(items=[], next_cursor=None)
        r = client.get("/api/v1/contributions", headers=AUTHED_HEADERS)
        assert r.status_code == 200

    def test_response_has_page_shape(self, client, contribution_service):
        contribution_service.read_many.return_value = Page(items=[], next_cursor=None)
        body = client.get("/api/v1/contributions", headers=AUTHED_HEADERS).json()
        assert "items" in body
        assert "next_cursor" in body

    def test_items_in_response(self, client, contribution_service):
        contribution_service.read_many.return_value = Page(items=[SAMPLE_CONTRIBUTION], next_cursor=None)
        body = client.get("/api/v1/contributions", headers=AUTHED_HEADERS).json()
        assert len(body["items"]) == 1

    def test_repo_called_with_pagination(self, client, contribution_service):
        contribution_service.read_many.return_value = Page(items=[], next_cursor=None)
        client.get("/api/v1/contributions", params={"limit": 10}, headers=AUTHED_HEADERS)
        _, kwargs = contribution_service.read_many.call_args
        assert kwargs["pagination"].limit == 10

    def test_fields_forwarded(self, client, contribution_service):
        contribution_service.read_many.return_value = Page(items=[], next_cursor=None)
        client.get("/api/v1/contributions", params={"_fields": ["formula"]}, headers=AUTHED_HEADERS)
        _, kwargs = contribution_service.read_many.call_args
        assert kwargs["fields"] is not None
        assert "formula" in kwargs["fields"]

    def test_invalid_fields_returns_422(self, client, contribution_service):
        contribution_service.read_many.return_value = Page(items=[], next_cursor=None)
        r = client.get("/api/v1/contributions", params={"_fields": "bad_field"}, headers=AUTHED_HEADERS)
        assert r.status_code == 422

    def test_anonymous_can_list(self, client, contribution_service):
        contribution_service.read_many.return_value = Page(items=[], next_cursor=None)
        r = client.get("/api/v1/contributions", headers=ANON_HEADERS)
        assert r.status_code == 200

    def test_filter_param_forwarded_to_repo(self, client, contribution_service):
        contribution_service.read_many.return_value = Page(items=[], next_cursor=None)
        client.get("/api/v1/contributions", params={"formula": "Fe2O3"}, headers=AUTHED_HEADERS)
        contribution_service.read_many.assert_called_once()
