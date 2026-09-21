"""HTTP-layer behaviour of the downloads router (GET /downloads/{id} and .../content).

These exercise the real FastAPI route wiring against a mocked ``DownloadService``: path/param
binding for the ObjectId handle, the ``require_user`` gate, and error-envelope mapping. The
queue lifecycle itself is covered against a real DB in ``tests/integration/db/test_download_queue``.
"""

from unittest.mock import AsyncMock

import pytest
from beanie import PydanticObjectId

from mpcontribs_api.domains.downloads.dependencies import get_download_service
from mpcontribs_api.domains.downloads.models import DownloadOut, JobStatus
from mpcontribs_api.exceptions import JobStatusError, NotFoundError
from tests.integration.conftest import AUTHED_HEADERS, FORCE_ANON_HEADERS


@pytest.fixture(autouse=True)
def _authenticate(client):
    """Downloads are authenticated-only; default the shared client to an authenticated identity.

    Anonymous rejection is covered explicitly below via FORCE_ANON_HEADERS.
    """
    client.headers.update(AUTHED_HEADERS)


@pytest.fixture
def download_service(test_app):
    mock = AsyncMock()
    test_app.dependency_overrides[get_download_service] = lambda: mock
    yield mock
    test_app.dependency_overrides.pop(get_download_service, None)


def _job(**overrides) -> DownloadOut:
    data = {
        "id": str(PydanticObjectId()),
        "s3_key": "contributions/" + "0" * 64 + ".jsonl.gz",
        "status": JobStatus.ready,
        "requester": "google:alice@example.com",
        "domain": "contributions",
        "fmt": "jsonl",
    }
    data.update(overrides)
    return DownloadOut(**data)


class TestReadOneRoute:
    def test_returns_ticket_for_owner(self, client, download_service):
        oid = PydanticObjectId()
        download_service.read_one.return_value = _job(id=str(oid))
        r = client.get(f"/api/v1/downloads/{oid}")
        assert r.status_code == 200
        assert r.json()["id"] == str(oid)

    def test_id_forwarded_to_service(self, client, download_service):
        oid = PydanticObjectId()
        download_service.read_one.return_value = _job(id=str(oid))
        client.get(f"/api/v1/downloads/{oid}")
        assert download_service.read_one.call_args.kwargs["download_id"] == oid

    def test_unknown_id_returns_200_null(self, client, download_service):
        # Matches the by-id GET convention across domains: a miss is 200 with a null body.
        download_service.read_one.return_value = None
        r = client.get(f"/api/v1/downloads/{PydanticObjectId()}")
        assert r.status_code == 200
        assert r.json() is None

    def test_malformed_id_returns_422(self, client, download_service):
        assert client.get("/api/v1/downloads/not-an-objectid").status_code == 422

    def test_anon_401(self, client, download_service):
        r = client.get(f"/api/v1/downloads/{PydanticObjectId()}", headers=FORCE_ANON_HEADERS)
        assert r.status_code == 401
        download_service.read_one.assert_not_called()


class TestContentRoute:
    """The presigned-url route must actually resolve at /downloads/{id}/content."""

    def test_returns_presigned_url(self, client, download_service):
        download_service.get_presigned_url.return_value = "https://signed.example/object"
        r = client.get(f"/api/v1/downloads/{PydanticObjectId()}/content")
        # Guards the historical missing-leading-slash bug: the route resolves (not 404).
        assert r.status_code == 200
        assert r.json() == "https://signed.example/object"

    def test_id_forwarded_to_service(self, client, download_service):
        oid = PydanticObjectId()
        download_service.get_presigned_url.return_value = "https://signed.example/object"
        client.get(f"/api/v1/downloads/{oid}/content")
        assert download_service.get_presigned_url.call_args.kwargs["download_id"] == oid

    def test_not_ready_surfaces_job_status_error(self, client, download_service):
        download_service.get_presigned_url.side_effect = JobStatusError("download status not 'ready'")
        r = client.get(f"/api/v1/downloads/{PydanticObjectId()}/content")
        assert r.status_code == 425
        assert r.json()["error"]["code"] == "job_status_error"

    def test_missing_download_returns_404(self, client, download_service):
        download_service.get_presigned_url.side_effect = NotFoundError("download not found")
        r = client.get(f"/api/v1/downloads/{PydanticObjectId()}/content")
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "not_found"

    def test_anon_401(self, client, download_service):
        r = client.get(f"/api/v1/downloads/{PydanticObjectId()}/content", headers=FORCE_ANON_HEADERS)
        assert r.status_code == 401
        download_service.get_presigned_url.assert_not_called()
