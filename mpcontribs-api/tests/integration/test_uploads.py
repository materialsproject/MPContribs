"""Route-wiring tests for the uploads API.

The :class:`UploadService` is replaced with an ``AsyncMock``, so these assert the HTTP surface —
routing, status codes, auth gating, request validation, and response serialization — independent of
S3/SQS/Mongo. The orchestration logic itself is covered in ``tests/unit/domains/test_upload_service.py``.
"""

import pytest
from beanie import PydanticObjectId

from mpcontribs_api.domains.uploads.dependencies import get_upload_service
from mpcontribs_api.domains.uploads.models import (
    FileInitiated,
    PartUrl,
    PartUrls,
    SessionInitiated,
    UploadCompleted,
    UploadOut,
)
from mpcontribs_api.pagination import Page
from tests.integration.conftest import AUTHED_HEADERS, FORCE_ANON_HEADERS

OID = "6eb7cf5a86d9755df3a6c593"

# A minimal valid manifest body for the happy-path POST: add_contributions accepts a lone
# contributions source file (create_project would additionally require a project-metadata file).
MANIFEST = {
    "project": "myproject",
    "operation": "add_contributions",
    "files": [
        {
            "filename": "contributions.csv",
            "role": "contributions",
            "format": "csv",
            "content_type": "text/csv",
            "size": 1024,
        }
    ],
}


@pytest.fixture
def upload_service(test_app):
    from unittest.mock import AsyncMock

    service = AsyncMock()
    test_app.dependency_overrides[get_upload_service] = lambda: service
    yield service
    test_app.dependency_overrides.pop(get_upload_service, None)


# ---------------------------------------------------------------------------
# GET /api/v1/uploads  (search) + GET /api/v1/uploads/{id}
# ---------------------------------------------------------------------------


class TestSearch:
    def test_list_returns_200(self, client, upload_service):
        upload_service.read_many.return_value = Page(
            items=[
                UploadOut(_id=PydanticObjectId(OID), project="myproject", operation="create_project", status="pending")
            ],
            next_cursor=None,
        )
        r = client.get("/api/v1/uploads", headers=AUTHED_HEADERS)
        assert r.status_code == 200
        assert r.json()["items"][0]["id"] == OID

    def test_list_passes_filter_through(self, client, upload_service):
        upload_service.read_many.return_value = Page(items=[], next_cursor=None)
        r = client.get("/api/v1/uploads?operation=create_project&status=completed", headers=AUTHED_HEADERS)
        assert r.status_code == 200
        filter_arg = upload_service.read_many.await_args.kwargs["filter"]
        assert filter_arg.operation == "create_project"
        assert filter_arg.status == "completed"

    def test_list_anonymous_rejected_401(self, client, upload_service):
        # Uploads are private: unlike public resources, listing requires authentication.
        r = client.get("/api/v1/uploads", headers=FORCE_ANON_HEADERS)
        assert r.status_code == 401
        upload_service.read_many.assert_not_called()

    def test_get_by_id_returns_200(self, client, upload_service):
        upload_service.read_one.return_value = UploadOut(
            _id=PydanticObjectId(OID), project="myproject", operation="create_project", status="pending"
        )
        r = client.get(f"/api/v1/uploads/{OID}", headers=AUTHED_HEADERS)
        assert r.status_code == 200
        assert r.json()["id"] == OID

    def test_get_by_id_absent_returns_null(self, client, upload_service):
        upload_service.read_one.return_value = None
        r = client.get(f"/api/v1/uploads/{OID}", headers=AUTHED_HEADERS)
        assert r.status_code == 200
        assert r.json() is None

    def test_get_by_id_anonymous_rejected_401(self, client, upload_service):
        r = client.get(f"/api/v1/uploads/{OID}", headers=FORCE_ANON_HEADERS)
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/v1/uploads
# ---------------------------------------------------------------------------


class TestInitiate:
    def test_manifest_returns_201_with_per_file_handles(self, client, upload_service):
        upload_service.initiate.return_value = SessionInitiated(
            id=PydanticObjectId(OID),
            operation="add_contributions",
            project="myproject",
            files=[
                FileInitiated(
                    name="contributions.csv",
                    key=f"myproject/{OID}/source/contributions.csv",
                    type="single",
                    num_parts=1,
                    part_size=1024,
                    url="https://signed.example/put",
                )
            ],
        )
        r = client.post("/api/v1/uploads", json=MANIFEST, headers=AUTHED_HEADERS)
        assert r.status_code == 201
        body = r.json()
        assert body["id"] == OID
        assert body["files"][0]["name"] == "contributions.csv"
        assert body["files"][0]["url"] == "https://signed.example/put"
        # the manifest was handed to the service as a parsed UploadManifest
        assert upload_service.initiate.await_args.kwargs["manifest"].project == "myproject"

    def test_anonymous_rejected_401(self, client, upload_service):
        r = client.post("/api/v1/uploads", json=MANIFEST, headers=FORCE_ANON_HEADERS)
        assert r.status_code == 401
        upload_service.initiate.assert_not_called()

    def test_empty_files_rejected_422(self, client, upload_service):
        r = client.post("/api/v1/uploads", json={**MANIFEST, "files": []}, headers=AUTHED_HEADERS)
        assert r.status_code == 422

    def test_unsafe_filename_rejected_422(self, client, upload_service):
        bad = {**MANIFEST, "files": [{**MANIFEST["files"][0], "filename": "a\\b.csv"}]}
        r = client.post("/api/v1/uploads", json=bad, headers=AUTHED_HEADERS)
        assert r.status_code == 422

    def test_non_positive_size_rejected_422(self, client, upload_service):
        bad = {**MANIFEST, "files": [{**MANIFEST["files"][0], "size": 0}]}
        r = client.post("/api/v1/uploads", json=bad, headers=AUTHED_HEADERS)
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/v1/uploads/{id}/files/{name}/parts
# ---------------------------------------------------------------------------


class TestGenerateParts:
    def test_returns_urls(self, client, upload_service):
        upload_service.generate_part_urls.return_value = PartUrls(
            urls=[PartUrl(part_number=2, url="https://signed.example/2")]
        )
        r = client.post(f"/api/v1/uploads/{OID}/files/big.csv/parts", json={"start_part": 2}, headers=AUTHED_HEADERS)
        assert r.status_code == 200
        assert r.json()["urls"][0]["part_number"] == 2
        assert upload_service.generate_part_urls.await_args.kwargs["name"] == "big.csv"

    def test_defaults_start_part_to_one(self, client, upload_service):
        upload_service.generate_part_urls.return_value = PartUrls(urls=[])
        r = client.post(f"/api/v1/uploads/{OID}/files/big.csv/parts", json={}, headers=AUTHED_HEADERS)
        assert r.status_code == 200
        assert upload_service.generate_part_urls.await_args.kwargs["start_part"] == 1

    def test_invalid_object_id_rejected_422(self, client, upload_service):
        r = client.post("/api/v1/uploads/not-an-oid/files/x.csv/parts", json={"start_part": 1}, headers=AUTHED_HEADERS)
        assert r.status_code == 422

    def test_anonymous_rejected_401(self, client, upload_service):
        r = client.post(
            f"/api/v1/uploads/{OID}/files/big.csv/parts", json={"start_part": 1}, headers=FORCE_ANON_HEADERS
        )
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/v1/uploads/{id}/complete
# ---------------------------------------------------------------------------


class TestComplete:
    def test_returns_completed(self, client, upload_service):
        upload_service.complete.return_value = UploadCompleted(id=PydanticObjectId(OID), status="completed")
        r = client.post(
            f"/api/v1/uploads/{OID}/complete",
            json={"files": [{"name": "big.csv", "parts": [{"part_number": 1, "etag": "e1"}]}]},
            headers=AUTHED_HEADERS,
        )
        assert r.status_code == 200
        assert r.json()["status"] == "completed"

    def test_files_default_to_empty(self, client, upload_service):
        upload_service.complete.return_value = UploadCompleted(id=PydanticObjectId(OID), status="completed")
        r = client.post(f"/api/v1/uploads/{OID}/complete", json={}, headers=AUTHED_HEADERS)
        assert r.status_code == 200
        assert upload_service.complete.await_args.kwargs["files"] == []

    def test_anonymous_rejected_401(self, client, upload_service):
        r = client.post(f"/api/v1/uploads/{OID}/complete", json={}, headers=FORCE_ANON_HEADERS)
        assert r.status_code == 401
