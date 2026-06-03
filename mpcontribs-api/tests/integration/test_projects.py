"""Integration tests for /api/v1/projects routes.

The project repository is overridden with an AsyncMock for each test so no
MongoDB connection is needed. Tests verify:
  - HTTP status codes
  - Response JSON shapes (Page envelope, ProjectOut fields)
  - That the correct repository method is called
  - That query parameters (_fields, pagination, filters) are forwarded
  - Error handling (NotFoundError → 404, etc.)
"""


import pytest

from src.mpcontribs_api.domains.projects.dependencies import get_scoped_projects
from src.mpcontribs_api.domains.projects.models import ProjectOut, Stats
from src.mpcontribs_api.exceptions import ConflictError, NotFoundError
from src.mpcontribs_api.pagination import Page
from tests.integration.conftest import ANON_HEADERS, AUTHED_HEADERS

# ---------------------------------------------------------------------------
# Shared sample data
# ---------------------------------------------------------------------------

SAMPLE_STATS = Stats(columns=1, contributions=5, tables=0, structures=0, attachments=0, size=128.0)

SAMPLE_PROJECT = ProjectOut.model_validate(
    {
        "_id": "mp-sample",
        "title": "Sample Project",
        "authors": "Alice, Bob",
        "description": "A sample",
        "is_public": True,
        "is_approved": True,
        "stats": SAMPLE_STATS,
    }
)


# ---------------------------------------------------------------------------
# Fixture: inject mock repo into the test_app for the duration of each test
# ---------------------------------------------------------------------------


@pytest.fixture
def project_repo(test_app, mock_project_repo):
    test_app.dependency_overrides[get_scoped_projects] = lambda: mock_project_repo
    yield mock_project_repo
    test_app.dependency_overrides.pop(get_scoped_projects, None)


# ---------------------------------------------------------------------------
# GET /api/v1/projects
# ---------------------------------------------------------------------------


class TestListProjects:
    def test_empty_page_returns_200(self, client, project_repo):
        project_repo.get_project.return_value = Page(items=[], next_cursor=None)
        r = client.get("/api/v1/projects", headers=AUTHED_HEADERS)
        assert r.status_code == 200

    def test_response_has_items_and_cursor(self, client, project_repo):
        project_repo.get_project.return_value = Page(items=[], next_cursor=None)
        body = client.get("/api/v1/projects", headers=AUTHED_HEADERS).json()
        assert "items" in body
        assert "next_cursor" in body

    def test_items_returned_in_response(self, client, project_repo):
        project_repo.get_project.return_value = Page(items=[SAMPLE_PROJECT], next_cursor=None)
        body = client.get("/api/v1/projects", headers=AUTHED_HEADERS).json()
        assert len(body["items"]) == 1

    def test_next_cursor_set_when_more_pages(self, client, project_repo):
        from src.mpcontribs_api.pagination import encode_cursor
        cursor = encode_cursor("mp-sample")
        project_repo.get_project.return_value = Page(items=[SAMPLE_PROJECT], next_cursor=cursor)
        body = client.get("/api/v1/projects", headers=AUTHED_HEADERS).json()
        assert body["next_cursor"] == cursor

    def test_repo_get_project_called(self, client, project_repo):
        project_repo.get_project.return_value = Page(items=[], next_cursor=None)
        client.get("/api/v1/projects", headers=AUTHED_HEADERS)
        project_repo.get_project.assert_called_once()

    def test_anonymous_user_reaches_route(self, client, project_repo):
        project_repo.get_project.return_value = Page(items=[], next_cursor=None)
        r = client.get("/api/v1/projects", headers=ANON_HEADERS)
        assert r.status_code == 200

    def test_invalid_fields_param_returns_422(self, client, project_repo):
        project_repo.get_project.return_value = Page(items=[], next_cursor=None)
        r = client.get("/api/v1/projects", params={"_fields": "nonexistent_field"}, headers=AUTHED_HEADERS)
        assert r.status_code == 422

    def test_limit_param_forwarded(self, client, project_repo):
        project_repo.get_project.return_value = Page(items=[], next_cursor=None)
        client.get("/api/v1/projects", params={"limit": 5}, headers=AUTHED_HEADERS)
        _, kwargs = project_repo.get_project.call_args
        assert kwargs["pagination"].limit == 5

    def test_limit_above_max_returns_422(self, client, project_repo):
        r = client.get("/api/v1/projects", params={"limit": 999}, headers=AUTHED_HEADERS)
        assert r.status_code == 422

    def test_valid_fields_param_forwarded(self, client, project_repo):
        project_repo.get_project.return_value = Page(items=[], next_cursor=None)
        client.get("/api/v1/projects", params={"_fields": "title,authors"}, headers=AUTHED_HEADERS)
        _, kwargs = project_repo.get_project.call_args
        assert kwargs["fields"] is not None
        assert "title" in kwargs["fields"]


# ---------------------------------------------------------------------------
# GET /api/v1/projects/{id}
# ---------------------------------------------------------------------------


class TestGetProjectById:
    def test_found_returns_200(self, client, project_repo):
        project_repo.get_project_by_id.return_value = SAMPLE_PROJECT
        r = client.get("/api/v1/projects/mp-sample", headers=AUTHED_HEADERS)
        assert r.status_code == 200

    def test_response_contains_project_data(self, client, project_repo):
        project_repo.get_project_by_id.return_value = SAMPLE_PROJECT
        body = client.get("/api/v1/projects/mp-sample", headers=AUTHED_HEADERS).json()
        assert body["id"] == "mp-sample"
        assert body["title"] == "Sample Project"

    def test_not_found_returns_404(self, client, project_repo):
        project_repo.get_project_by_id.side_effect = NotFoundError("project not found")
        r = client.get("/api/v1/projects/nonexistent", headers=AUTHED_HEADERS)
        assert r.status_code == 404

    def test_not_found_error_code(self, client, project_repo):
        project_repo.get_project_by_id.side_effect = NotFoundError("project not found")
        body = client.get("/api/v1/projects/nonexistent", headers=AUTHED_HEADERS).json()
        assert body["error"]["code"] == "not_found"

    def test_id_forwarded_to_repo(self, client, project_repo):
        project_repo.get_project_by_id.return_value = SAMPLE_PROJECT
        client.get("/api/v1/projects/my-specific-id", headers=AUTHED_HEADERS)
        _, kwargs = project_repo.get_project_by_id.call_args
        assert kwargs["id"] == "my-specific-id"

    def test_fields_param_forwarded(self, client, project_repo):
        project_repo.get_project_by_id.return_value = SAMPLE_PROJECT
        client.get("/api/v1/projects/mp-sample", params={"_fields": "title"}, headers=AUTHED_HEADERS)
        _, kwargs = project_repo.get_project_by_id.call_args
        assert kwargs["fields"] is not None
        assert "title" in kwargs["fields"]

    def test_no_fields_param_passes_none(self, client, project_repo):
        project_repo.get_project_by_id.return_value = SAMPLE_PROJECT
        client.get("/api/v1/projects/mp-sample", headers=AUTHED_HEADERS)
        _, kwargs = project_repo.get_project_by_id.call_args
        assert kwargs["fields"] is None


# ---------------------------------------------------------------------------
# PATCH /api/v1/projects/{id}
# ---------------------------------------------------------------------------


class TestPatchProject:
    def test_valid_patch_returns_200(self, client, project_repo):
        project_repo.patch_project.return_value = SAMPLE_PROJECT
        r = client.patch(
            "/api/v1/projects/mp-sample",
            json={"title": "Updated Title"},
            headers=AUTHED_HEADERS,
        )
        assert r.status_code == 200

    def test_patch_response_is_project_out(self, client, project_repo):
        updated = ProjectOut(id="mp-sample", title="Updated Title")
        project_repo.patch_project.return_value = updated
        body = client.patch(
            "/api/v1/projects/mp-sample",
            json={"title": "Updated Title"},
            headers=AUTHED_HEADERS,
        ).json()
        assert body["title"] == "Updated Title"

    def test_not_found_returns_404(self, client, project_repo):
        project_repo.patch_project.side_effect = NotFoundError("not found")
        r = client.patch(
            "/api/v1/projects/missing",
            json={"title": "x" * 5},
            headers=AUTHED_HEADERS,
        )
        assert r.status_code == 404

    def test_invalid_title_too_short_returns_422(self, client, project_repo):
        r = client.patch(
            "/api/v1/projects/mp-sample",
            json={"title": "ab"},
            headers=AUTHED_HEADERS,
        )
        assert r.status_code == 422

    def test_id_and_update_forwarded_to_repo(self, client, project_repo):
        project_repo.patch_project.return_value = SAMPLE_PROJECT
        client.patch(
            "/api/v1/projects/mp-sample",
            json={"title": "New Name"},
            headers=AUTHED_HEADERS,
        )
        _, kwargs = project_repo.patch_project.call_args
        assert kwargs["id"] == "mp-sample"
        assert kwargs["update"].title == "New Name"


# ---------------------------------------------------------------------------
# DELETE /api/v1/projects/{id}
# ---------------------------------------------------------------------------


class TestDeleteProject:
    def test_delete_returns_204(self, client, project_repo):
        project_repo.delete_project.return_value = None
        r = client.delete("/api/v1/projects/mp-sample", headers=AUTHED_HEADERS)
        assert r.status_code == 204

    def test_delete_response_has_no_body(self, client, project_repo):
        project_repo.delete_project.return_value = None
        r = client.delete("/api/v1/projects/mp-sample", headers=AUTHED_HEADERS)
        assert r.content == b""

    def test_id_forwarded_to_repo(self, client, project_repo):
        project_repo.delete_project.return_value = None
        client.delete("/api/v1/projects/mp-sample", headers=AUTHED_HEADERS)
        _, kwargs = project_repo.delete_project.call_args
        assert kwargs["id"] == "mp-sample"


# ---------------------------------------------------------------------------
# PUT /api/v1/projects/{id}
# ---------------------------------------------------------------------------


class TestUpsertProject:
    def _valid_body(self, **overrides):
        body = {
            "_id": "mp-sample",
            "title": "Test Project",
            "authors": "Alice",
            "description": "A project",
            "owner": "google:alice@example.com",
            "unique_identifiers": True,
            "stats": {"columns": 0, "contributions": 0, "tables": 0, "structures": 0, "attachments": 0, "size": 0.0},
        }
        body.update(overrides)
        return body

    def test_valid_upsert_returns_200(self, client, project_repo):
        project_repo.upsert_project.return_value = SAMPLE_PROJECT
        r = client.put("/api/v1/projects/mp-sample", json=self._valid_body(), headers=AUTHED_HEADERS)
        assert r.status_code == 200

    def test_conflict_returns_409(self, client, project_repo):
        project_repo.upsert_project.side_effect = ConflictError("already exists")
        r = client.put("/api/v1/projects/mp-sample", json=self._valid_body(), headers=AUTHED_HEADERS)
        assert r.status_code == 409

    def test_missing_required_field_returns_422(self, client, project_repo):
        body = self._valid_body()
        del body["title"]
        r = client.put("/api/v1/projects/mp-sample", json=body, headers=AUTHED_HEADERS)
        assert r.status_code == 422
