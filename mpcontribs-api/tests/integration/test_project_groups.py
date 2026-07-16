from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from mpcontribs_api.domains.project_groups.dependencies import get_project_group_repository
from tests.integration.conftest import AUTHED_HEADERS

# A valid 24-char hex ObjectId string (ProjectGroupOut.id is a PydanticObjectId).
SAMPLE_OID = "6eb7cf5a86d9755df3a6c593"


@pytest.fixture
def group_repo(test_app):
    repo = AsyncMock()
    test_app.dependency_overrides[get_project_group_repository] = lambda: repo
    yield repo
    test_app.dependency_overrides.pop(get_project_group_repository, None)


# ---------------------------------------------------------------------------
# POST /api/v1/project_groups
#
# The handler returns the stored document, which FastAPI coerces into
# ProjectGroupOut with from_attributes=True. A Beanie Document exposes ``.id``
# (not ``._id``), so the response model must populate its id by field name as
# well as the ``_id`` alias — otherwise every create/update response would
# serialise ``id: null`` and callers couldn't see what id their group got.
# ---------------------------------------------------------------------------


class TestInsertProjectGroupResponse:
    def _body(self, **overrides):
        body = {
            "name": "my-group",
            "owner": "google:alice@example.com",
            "description": "d",
            "projects": [],
        }
        body.update(overrides)
        return body

    def _inserted(self, **overrides):
        """Stand-in for the stored document: exposes ``.id`` like a Beanie Document."""
        attrs = {
            "id": SAMPLE_OID,
            "name": "my-group",
            "owner": "google:alice@example.com",
            "is_public": False,
            "projects": None,
            "description": "d",
        }
        attrs.update(overrides)
        return SimpleNamespace(**attrs)

    def test_returns_201(self, client, group_repo):
        group_repo.insert_project_group.return_value = self._inserted()
        r = client.post("/api/v1/project_groups", json=self._body(), headers=AUTHED_HEADERS)
        assert r.status_code == 201

    def test_response_includes_generated_id(self, client, group_repo):
        group_repo.insert_project_group.return_value = self._inserted()
        body = client.post("/api/v1/project_groups", json=self._body(), headers=AUTHED_HEADERS).json()
        assert body["id"] == SAMPLE_OID

    def test_response_echoes_full_document(self, client, group_repo):
        group_repo.insert_project_group.return_value = self._inserted(name="echo-group", is_public=True)
        body = client.post(
            "/api/v1/project_groups",
            json=self._body(name="echo-group", is_public=True),
            headers=AUTHED_HEADERS,
        ).json()
        assert body["id"] == SAMPLE_OID
        assert body["name"] == "echo-group"
        assert body["owner"] == "google:alice@example.com"
        assert body["is_public"] is True
