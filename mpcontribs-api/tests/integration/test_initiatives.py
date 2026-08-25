from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from mpcontribs_api.domains.initiatives.dependencies import get_initiative_service
from mpcontribs_api.exceptions import NotFoundError
from mpcontribs_api.pagination import Page
from tests.integration.conftest import AUTHED_HEADERS, FORCE_ANON_HEADERS

SAMPLE_OID = "6eb7cf5a86d9755df3a6c593"


@pytest.fixture
def initiative_service(test_app):
    service = AsyncMock()
    test_app.dependency_overrides[get_initiative_service] = lambda: service
    yield service
    test_app.dependency_overrides.pop(get_initiative_service, None)


def _stored(**overrides):
    """Stand-in for the stored document: exposes ``.id`` like a Beanie Document."""
    attrs = {
        "id": SAMPLE_OID,
        "slug": "battery-genome",
        "name": "Battery Genome",
        "owner": "google:alice@example.com",
        "is_public": False,
        "is_approved": False,
    }
    attrs.update(overrides)
    return SimpleNamespace(**attrs)


# ---------------------------------------------------------------------------
# POST /api/v1/initiatives
# ---------------------------------------------------------------------------


class TestInsert:
    def test_returns_201_and_echoes_id(self, client, initiative_service):
        initiative_service.insert_one.return_value = _stored()
        r = client.post(
            "/api/v1/initiatives",
            json={"slug": "battery-genome", "name": "Battery Genome"},
            headers=AUTHED_HEADERS,
        )
        assert r.status_code == 201
        assert r.json()["id"] == SAMPLE_OID

    def test_anonymous_rejected_401(self, client, initiative_service):
        r = client.post(
            "/api/v1/initiatives",
            json={"slug": "battery-genome", "name": "Battery Genome"},
            headers=FORCE_ANON_HEADERS,
        )
        assert r.status_code == 401

    def test_invalid_slug_returns_422(self, client, initiative_service):
        r = client.post(
            "/api/v1/initiatives",
            json={"slug": "Not A Slug!", "name": "x"},
            headers=AUTHED_HEADERS,
        )
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/v1/initiatives (+ /{slug})
# ---------------------------------------------------------------------------


class TestGet:
    def test_list_returns_200(self, client, initiative_service):
        initiative_service.read_many.return_value = Page(items=[], next_cursor=None)
        r = client.get("/api/v1/initiatives", headers=AUTHED_HEADERS)
        assert r.status_code == 200

    def test_get_by_slug_returns_200(self, client, initiative_service):
        initiative_service.read_one.return_value = _stored()
        r = client.get("/api/v1/initiatives/battery-genome", headers=AUTHED_HEADERS)
        assert r.status_code == 200
        assert r.json()["slug"] == "battery-genome"


# ---------------------------------------------------------------------------
# PATCH /api/v1/initiatives/{slug}
# ---------------------------------------------------------------------------


class TestPatch:
    def test_patch_returns_200(self, client, initiative_service):
        initiative_service.update_one.return_value = _stored(name="Renamed")
        r = client.patch(
            "/api/v1/initiatives/battery-genome",
            json={"name": "Renamed"},
            headers=AUTHED_HEADERS,
        )
        assert r.status_code == 200
        assert r.json()["name"] == "Renamed"

    def test_anonymous_rejected_401(self, client, initiative_service):
        r = client.patch(
            "/api/v1/initiatives/battery-genome",
            json={"name": "Renamed"},
            headers=FORCE_ANON_HEADERS,
        )
        assert r.status_code == 401

    def test_not_found_propagates_404(self, client, initiative_service):
        initiative_service.update_one.side_effect = NotFoundError("nope")
        r = client.patch(
            "/api/v1/initiatives/missing",
            json={"name": "Renamed"},
            headers=AUTHED_HEADERS,
        )
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/v1/initiatives/{slug}
# ---------------------------------------------------------------------------


class TestDelete:
    def test_delete_returns_204(self, client, initiative_service):
        initiative_service.delete_one.return_value = None
        r = client.delete("/api/v1/initiatives/battery-genome", headers=AUTHED_HEADERS)
        assert r.status_code == 204
        assert r.content == b""

    def test_anonymous_rejected_401(self, client, initiative_service):
        r = client.delete("/api/v1/initiatives/battery-genome", headers=FORCE_ANON_HEADERS)
        assert r.status_code == 401
