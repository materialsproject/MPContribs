"""Tests for the per-request bulk-write count guard and the GET /limits contract endpoint."""

import pytest
from beanie import PydanticObjectId

from mpcontribs_api.config import get_settings
from mpcontribs_api.domains._shared.bulk import BulkWriteSummary
from mpcontribs_api.domains.contributions.dependencies import get_contribution_service
from tests.integration.conftest import AUTHED_HEADERS


def _valid_contribution_body(**overrides) -> dict:
    body = {
        "_id": str(PydanticObjectId()),
        "project": "test-project",
        "identifier": "mp-1234",
        "formula": "Fe2O3",
        "data": {"band_gap": 2.1},
    }
    body.update(overrides)
    return body


@pytest.fixture
def contribution_service(test_app, mock_contribution_service):
    test_app.dependency_overrides[get_contribution_service] = lambda: mock_contribution_service
    yield mock_contribution_service
    test_app.dependency_overrides.pop(get_contribution_service, None)


@pytest.fixture(autouse=True)
def _authenticate(client):
    client.headers.update(AUTHED_HEADERS)


class TestBulkWriteLimit:
    @pytest.fixture(autouse=True)
    def _small_limit(self, monkeypatch):
        # Shrink the limit so the test doesn't need to build 1000+ bodies.
        monkeypatch.setattr(get_settings().mongo, "bulk_write_limit", 2)

    def test_over_limit_post_returns_422(self, client, contribution_service):
        body = [_valid_contribution_body() for _ in range(3)]
        r = client.post("/api/v1/contributions", json=body)
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "validation_error"
        contribution_service.insert_contributions.assert_not_called()

    def test_at_limit_post_passes(self, client, contribution_service):
        contribution_service.insert_contributions.return_value = BulkWriteSummary(total=2, succeeded=[], failed=[])
        body = [_valid_contribution_body() for _ in range(2)]
        r = client.post("/api/v1/contributions", json=body)
        assert r.status_code == 200
        contribution_service.insert_contributions.assert_called_once()

    def test_over_limit_put_returns_422(self, client, contribution_service):
        body = [_valid_contribution_body() for _ in range(3)]
        r = client.put("/api/v1/contributions", json=body)
        assert r.status_code == 422
        contribution_service.upsert_contributions.assert_not_called()


class TestLimitsEndpoint:
    def test_limits_reports_configured_values(self, client):
        mongo = get_settings().mongo
        r = client.get("/api/v1/limits")
        assert r.status_code == 200
        assert r.json() == {
            "max_request_bytes": mongo.max_request_bytes,
            "bulk_write_limit": mongo.bulk_write_limit,
            "max_components_per_contribution": mongo.max_components_per_contribution,
            "component_insert_chunk_size": mongo.component_insert_chunk_size,
        }

    def test_limits_is_public(self, client):
        # No auth headers: still readable (public metadata).
        client.headers.clear()
        assert client.get("/api/v1/limits").status_code == 200
