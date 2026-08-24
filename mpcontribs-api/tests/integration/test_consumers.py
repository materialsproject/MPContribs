from unittest.mock import AsyncMock

import pytest

from mpcontribs_api.domains.consumers.dependencies import get_consumer_service
from mpcontribs_api.domains.consumers.models import ConsumerOut, ConsumerSettings
from mpcontribs_api.pagination import Page
from tests.integration.conftest import ADMIN_HEADERS, ANON_HEADERS, AUTHED_HEADERS

# ---------------------------------------------------------------------------
# The consumer-override routes are admin-only: the whole router carries
# ``dependencies=[Depends(require_admin)]``. These tests guard that wiring — an
# anonymous caller gets 401, an authenticated non-admin gets 403 — and confirm
# the admin path reaches the (mocked) service. The service is mocked because the
# guard runs *before* the service dependency resolves.
# ---------------------------------------------------------------------------

SAMPLE_CONSUMER = ConsumerOut(
    id="507f1f77bcf86cd799439011",
    consumer_id="test-consumer-id",
    settings=ConsumerSettings(max_projects=3, max_unapproved_contributions_per_project=10, max_columns=20),
)


@pytest.fixture
def consumer_service(test_app):
    """Override the service every consumer route depends on with an async mock."""
    service = AsyncMock()
    test_app.dependency_overrides[get_consumer_service] = lambda: service
    yield service
    test_app.dependency_overrides.pop(get_consumer_service, None)


def _requests(client):
    """Every (label, callable) mutating/reading request under the consumers router.

    Each callable takes the request headers so the same set can be replayed as anon, non-admin,
    and admin.
    """
    return [
        ("get_many", lambda h: client.get("/api/v1/admin/consumers", headers=h)),
        ("get_one", lambda h: client.get("/api/v1/admin/consumers/507f1f77bcf86cd799439011", headers=h)),
        ("insert_one", lambda h: client.post("/api/v1/admin/consumers", json={"consumer_id": "c-new"}, headers=h)),
        (
            "patch_one",
            lambda h: client.patch(
                "/api/v1/admin/consumers/507f1f77bcf86cd799439011",
                json={"settings": {"max_projects": 5}},
                headers=h,
            ),
        ),
        ("delete_one", lambda h: client.delete("/api/v1/admin/consumers/507f1f77bcf86cd799439011", headers=h)),
    ]


# ---------------------------------------------------------------------------
# Admin-only guard: anonymous -> 401, authenticated non-admin -> 403
# ---------------------------------------------------------------------------


class TestConsumerRoutesRequireAdmin:
    @pytest.mark.parametrize("label", ["get_many", "get_one", "insert_one", "patch_one", "delete_one"])
    def test_anonymous_rejected_401(self, client, consumer_service, label):
        request = dict(_requests(client))[label]
        r = request(ANON_HEADERS)
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "authentication_error"
        getattr(consumer_service, label).assert_not_called()

    @pytest.mark.parametrize("label", ["get_many", "get_one", "insert_one", "patch_one", "delete_one"])
    def test_authenticated_non_admin_rejected_403(self, client, consumer_service, label):
        # AUTHED_HEADERS is an authenticated, non-admin caller (alice / mp-team).
        request = dict(_requests(client))[label]
        r = request(AUTHED_HEADERS)
        assert r.status_code == 403
        getattr(consumer_service, label).assert_not_called()


# ---------------------------------------------------------------------------
# Admin path reaches the service (happy-path wiring)
# ---------------------------------------------------------------------------


class TestConsumerRoutesAdminAllowed:
    def test_admin_get_many_returns_200(self, client, consumer_service):
        consumer_service.get_many.return_value = Page(items=[SAMPLE_CONSUMER], next_cursor=None)
        r = client.get("/api/v1/admin/consumers", headers=ADMIN_HEADERS)
        assert r.status_code == 200
        consumer_service.get_many.assert_called_once()

    def test_admin_get_one_returns_200(self, client, consumer_service):
        consumer_service.get_one.return_value = SAMPLE_CONSUMER
        r = client.get("/api/v1/admin/consumers/507f1f77bcf86cd799439011", headers=ADMIN_HEADERS)
        assert r.status_code == 200

    def test_admin_insert_returns_201(self, client, consumer_service):
        consumer_service.insert_one.return_value = SAMPLE_CONSUMER
        r = client.post("/api/v1/admin/consumers", json={"consumer_id": "test-consumer-id"}, headers=ADMIN_HEADERS)
        assert r.status_code == 201
        consumer_service.insert_one.assert_called_once()

    def test_admin_patch_returns_200(self, client, consumer_service):
        consumer_service.patch_one.return_value = SAMPLE_CONSUMER
        r = client.patch(
            "/api/v1/admin/consumers/507f1f77bcf86cd799439011",
            json={"settings": {"max_projects": 5}},
            headers=ADMIN_HEADERS,
        )
        assert r.status_code == 200
        consumer_service.patch_one.assert_called_once()

    def test_admin_delete_returns_204(self, client, consumer_service):
        consumer_service.delete_one.return_value = None
        r = client.delete("/api/v1/admin/consumers/507f1f77bcf86cd799439011", headers=ADMIN_HEADERS)
        assert r.status_code == 204
        consumer_service.delete_one.assert_called_once()
