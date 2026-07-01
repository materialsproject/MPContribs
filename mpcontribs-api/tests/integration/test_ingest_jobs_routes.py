"""Tests for the async bulk-ingestion scaffold routes (submit / status).

The worker is a stub, so these exercise only the route surface: 202 on submit, a persisted
pending job, idempotency replay, auth, and status lookup (found / not-found / bad id).
"""

from unittest.mock import AsyncMock

import pytest
from beanie import PydanticObjectId

from mpcontribs_api.domains.ingest_jobs.dependencies import get_ingest_job_repository
from mpcontribs_api.domains.ingest_jobs.models import IngestJob
from tests.integration.conftest import AUTHED_HEADERS, FORCE_ANON_HEADERS

BULK_URL = "/api/v1/contributions/bulk"


def _job(**overrides) -> IngestJob:
    fields = {
        "id": PydanticObjectId(),
        "owner": "google:alice@example.com",
        "status": "pending",
        "source": None,
        "idempotency_key": None,
    }
    fields.update(overrides)
    return IngestJob(**fields)


@pytest.fixture
def ingest_repo(test_app):
    repo = AsyncMock()
    test_app.dependency_overrides[get_ingest_job_repository] = lambda: repo
    yield repo
    test_app.dependency_overrides.pop(get_ingest_job_repository, None)


@pytest.fixture(autouse=True)
def _authenticate(client):
    client.headers.update(AUTHED_HEADERS)


class TestSubmitBulkIngest:
    def test_submit_returns_202_and_pending_job(self, client, ingest_repo):
        job = _job()
        ingest_repo.create_job.return_value = job
        r = client.post(BULK_URL, json={"source": None})
        assert r.status_code == 202
        body = r.json()
        assert body["id"] == str(job.id)
        assert body["status"] == "pending"
        ingest_repo.create_job.assert_awaited_once()

    def test_submit_requires_auth(self, client, test_app):
        # No repo override here: the repository dependency runs require_user, which rejects anon.
        r = client.post(BULK_URL, json={"source": None}, headers=FORCE_ANON_HEADERS)
        assert r.status_code == 401

    def test_idempotency_key_replays_existing_job(self, client, ingest_repo):
        existing = _job(idempotency_key="abc123")
        ingest_repo.find_by_idempotency_key.return_value = existing
        r = client.post(BULK_URL, json={"source": None}, headers={"Idempotency-Key": "abc123"})
        assert r.status_code == 202
        assert r.json()["id"] == str(existing.id)
        ingest_repo.find_by_idempotency_key.assert_awaited_once_with("abc123")
        ingest_repo.create_job.assert_not_called()


class TestGetBulkIngestJob:
    def test_get_existing_job(self, client, ingest_repo):
        job = _job(status="running", total=10, succeeded=4)
        ingest_repo.get_job.return_value = job
        r = client.get(f"{BULK_URL}/{job.id}")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "running"
        assert body["total"] == 10
        assert body["succeeded"] == 4

    def test_unknown_job_returns_404(self, client, ingest_repo):
        ingest_repo.get_job.return_value = None
        r = client.get(f"{BULK_URL}/{PydanticObjectId()}")
        assert r.status_code == 404

    def test_invalid_job_id_returns_422(self, client, ingest_repo):
        r = client.get(f"{BULK_URL}/not-an-object-id")
        assert r.status_code == 422
        ingest_repo.get_job.assert_not_called()
