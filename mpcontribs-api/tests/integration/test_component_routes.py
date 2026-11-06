from unittest.mock import AsyncMock

import pytest
from beanie import PydanticObjectId

from mpcontribs_api.domains.attachments.dependencies import get_attachment_service
from mpcontribs_api.domains.attachments.models import AttachmentOut
from mpcontribs_api.domains.structures.dependencies import get_structure_service
from mpcontribs_api.domains.structures.models import StructureOut
from mpcontribs_api.domains.tables.dependencies import get_table_service
from mpcontribs_api.domains.tables.models import TableOut
from mpcontribs_api.pagination import Page
from tests.integration.conftest import FORCE_ANON_HEADERS

# ---------------------------------------------------------------------------
# Every component endpoint routes through the unified (read-only) ComponentService,
# so each domain has a single mock service override. Components are immutable and
# worker-written: the routers expose reads only (list, /item, /{id}, /{id}/content);
# all writes/deletes/downloads flow through /uploads and are absent here (405).
# ---------------------------------------------------------------------------

HASH = "a" * 64


@pytest.fixture
def structure_service(test_app):
    mock = AsyncMock()
    test_app.dependency_overrides[get_structure_service] = lambda: mock
    yield mock
    test_app.dependency_overrides.pop(get_structure_service, None)


@pytest.fixture
def table_service(test_app):
    mock = AsyncMock()
    test_app.dependency_overrides[get_table_service] = lambda: mock
    yield mock
    test_app.dependency_overrides.pop(get_table_service, None)


@pytest.fixture
def attachment_service(test_app):
    mock = AsyncMock()
    test_app.dependency_overrides[get_attachment_service] = lambda: mock
    yield mock
    test_app.dependency_overrides.pop(get_attachment_service, None)


SAMPLE_STRUCTURE = StructureOut(project="my_project", hash=HASH, size=2048, ext="cif")
SAMPLE_TABLE = TableOut(project="my_project", hash=HASH, size=4096, ext="parquet", num_rows=2, title="Band gaps")
SAMPLE_ATTACHMENT = AttachmentOut(project="my_project", hash=HASH, size=1024, ext="gz", mime="application/gzip")


# ===========================================================================
# STRUCTURES
# ===========================================================================


class TestStructuresList:
    def test_empty_page_returns_200(self, client, structure_service):
        structure_service.read_many.return_value = Page(items=[], next_cursor=None)
        assert client.get("/api/v1/structures").status_code == 200

    def test_page_shape(self, client, structure_service):
        structure_service.read_many.return_value = Page(items=[SAMPLE_STRUCTURE], next_cursor="c")
        body = client.get("/api/v1/structures").json()
        assert "items" in body
        assert body["next_cursor"] == "c"

    def test_service_called_with_pagination(self, client, structure_service):
        structure_service.read_many.return_value = Page(items=[], next_cursor=None)
        client.get("/api/v1/structures?limit=5")
        assert structure_service.read_many.call_args.kwargs["pagination"].limit == 5

    def test_invalid_fields_returns_422(self, client, structure_service):
        structure_service.read_many.return_value = Page(items=[], next_cursor=None)
        assert client.get("/api/v1/structures?_fields=not_a_field").status_code == 422

    def test_index_fields_are_selectable(self, client, structure_service):
        # The thin index exposes project/hash/size/ext; content is served separately from S3.
        structure_service.read_many.return_value = Page(items=[], next_cursor=None)
        r = client.get("/api/v1/structures?_fields=hash&_fields=size")
        assert r.status_code == 200
        assert structure_service.read_many.call_args.kwargs["fields"] == frozenset({"id", "hash", "size"})


class TestStructuresByIdRouting:
    def test_get_by_id_conventional_path(self, client, structure_service):
        structure_service.read_one.return_value = SAMPLE_STRUCTURE
        assert client.get(f"/api/v1/structures/{PydanticObjectId()}").status_code == 200

    def test_content_endpoint_redirects_to_presigned_url(self, client, structure_service):
        # ``GET /{id}/content`` mints a presigned GET URL and 307-redirects; the object streams from S3.
        presigned = "https://bucket.s3.amazonaws.com/mpcontribs/proj/components/structures/abc.cif?X-Amz-Signature=d"
        structure_service.read_content.return_value = presigned
        r = client.get(f"/api/v1/structures/{PydanticObjectId()}/content", follow_redirects=False)
        assert r.status_code == 307
        assert r.headers["location"] == presigned


class TestStructuresByIdentityRouting:
    """``/item?project=&hash=`` addresses a structure by its content-addressed natural key."""

    IDENTITY = {"project": "my_project", "hash": HASH}

    def test_get_by_identity_forwards_identifiers(self, client, structure_service):
        structure_service.read_one.return_value = SAMPLE_STRUCTURE
        r = client.get("/api/v1/structures/item", params=self.IDENTITY)
        assert r.status_code == 200
        assert structure_service.read_one.await_args.kwargs["identifiers"] == self.IDENTITY

    def test_item_is_not_captured_as_an_id(self, client, structure_service):
        # ``/item`` must route to the identity handler, not match as ``/{id}`` with id="item".
        structure_service.read_one.return_value = SAMPLE_STRUCTURE
        client.get("/api/v1/structures/item", params=self.IDENTITY)
        assert structure_service.read_one.await_args.kwargs["identifiers"] == self.IDENTITY


class TestStructuresAreReadOnly:
    # Creation/replacement/deletion flow through /uploads; the component routers carry no write verbs.
    def test_post_not_allowed(self, client, structure_service):
        assert client.post("/api/v1/structures", json=[]).status_code == 405

    def test_patch_by_id_not_allowed(self, client, structure_service):
        assert client.patch(f"/api/v1/structures/{PydanticObjectId()}", json={}).status_code == 405

    def test_delete_batch_not_allowed(self, client, structure_service):
        assert client.delete("/api/v1/structures").status_code == 405

    def test_delete_by_id_not_allowed(self, client, structure_service):
        assert client.delete(f"/api/v1/structures/{PydanticObjectId()}").status_code == 405


# ===========================================================================
# TABLES
# ===========================================================================


class TestTablesList:
    def test_empty_page_returns_200(self, client, table_service):
        table_service.read_many.return_value = Page(items=[], next_cursor=None)
        assert client.get("/api/v1/tables").status_code == 200

    def test_page_shape(self, client, table_service):
        table_service.read_many.return_value = Page(items=[SAMPLE_TABLE], next_cursor=None)
        assert "items" in client.get("/api/v1/tables").json()

    def test_invalid_fields_returns_422(self, client, table_service):
        table_service.read_many.return_value = Page(items=[], next_cursor=None)
        assert client.get("/api/v1/tables?_fields=nope").status_code == 422


class TestTablesByIdRouting:
    def test_get_by_id_conventional_path(self, client, table_service):
        table_service.read_one.return_value = SAMPLE_TABLE
        assert client.get(f"/api/v1/tables/{PydanticObjectId()}").status_code == 200

    def test_content_endpoint_redirects_to_presigned_url(self, client, table_service):
        presigned = "https://bucket.s3.amazonaws.com/mpcontribs/proj/components/tables/abc.parquet?X-Amz-Signature=d"
        table_service.read_content.return_value = presigned
        r = client.get(f"/api/v1/tables/{PydanticObjectId()}/content", follow_redirects=False)
        assert r.status_code == 307
        assert r.headers["location"] == presigned


class TestTablesByIdentityRouting:
    def test_get_by_identity_forwards_identifiers(self, client, table_service):
        table_service.read_one.return_value = SAMPLE_TABLE
        r = client.get("/api/v1/tables/item", params={"project": "my_project", "hash": HASH})
        assert r.status_code == 200
        assert table_service.read_one.await_args.kwargs["identifiers"] == {"project": "my_project", "hash": HASH}


class TestTablesAreReadOnly:
    def test_post_not_allowed(self, client, table_service):
        assert client.post("/api/v1/tables", json=[]).status_code == 405

    def test_delete_batch_not_allowed(self, client, table_service):
        assert client.delete("/api/v1/tables").status_code == 405

    def test_delete_by_id_not_allowed(self, client, table_service):
        assert client.delete(f"/api/v1/tables/{PydanticObjectId()}").status_code == 405


# ===========================================================================
# ATTACHMENTS
# ===========================================================================


class TestAttachmentsRouterWiring:
    def test_list_calls_attachment_service(self, client, attachment_service):
        attachment_service.read_many.return_value = Page(items=[], next_cursor=None)
        r = client.get("/api/v1/attachments")
        assert r.status_code == 200
        attachment_service.read_many.assert_awaited_once()

    def test_get_by_id_calls_attachment_service(self, client, attachment_service):
        attachment_service.read_one.return_value = None
        client.get(f"/api/v1/attachments/{PydanticObjectId()}")
        attachment_service.read_one.assert_awaited_once()

    def test_content_endpoint_redirects_to_presigned_url(self, client, attachment_service):
        presigned = "https://bucket.s3.amazonaws.com/mpcontribs/proj/components/attachments/abc.gz?X-Amz-Signature=d"
        attachment_service.read_content.return_value = presigned
        r = client.get(f"/api/v1/attachments/{PydanticObjectId()}/content", follow_redirects=False)
        assert r.status_code == 307
        assert r.headers["location"] == presigned

    def test_get_by_identity_forwards_identifiers(self, client, attachment_service):
        attachment_service.read_one.return_value = SAMPLE_ATTACHMENT
        client.get("/api/v1/attachments/item", params={"project": "my_project", "hash": HASH})
        assert attachment_service.read_one.await_args.kwargs["identifiers"] == {"project": "my_project", "hash": HASH}


class TestAttachmentsAreReadOnly:
    # Attachments joined the S3-first component model: no inline insert, patch, delete, or download.
    def test_patch_by_id_not_allowed(self, client, attachment_service):
        assert client.patch(f"/api/v1/attachments/{PydanticObjectId()}", json={}).status_code == 405

    def test_delete_by_id_not_allowed(self, client, attachment_service):
        assert client.delete(f"/api/v1/attachments/{PydanticObjectId()}").status_code == 405

    def test_batch_delete_not_allowed(self, client, attachment_service):
        assert client.delete("/api/v1/attachments").status_code == 405

    def test_download_not_allowed(self, client, attachment_service):
        # The Mongo-sourced gzip download is gone; bulk export flows through /uploads.
        assert client.get("/api/v1/attachments/download/gz?format=jsonl").status_code == 404


# ===========================================================================
# Reads stay open to anonymous callers
# ===========================================================================


class TestComponentReadsOpenToAnon:
    def test_structures_get_open_to_anon(self, client, structure_service):
        structure_service.read_many.return_value = Page(items=[], next_cursor=None)
        assert client.get("/api/v1/structures", headers=FORCE_ANON_HEADERS).status_code == 200

    def test_tables_get_open_to_anon(self, client, table_service):
        table_service.read_many.return_value = Page(items=[], next_cursor=None)
        assert client.get("/api/v1/tables", headers=FORCE_ANON_HEADERS).status_code == 200

    def test_attachments_get_open_to_anon(self, client, attachment_service):
        attachment_service.read_many.return_value = Page(items=[], next_cursor=None)
        assert client.get("/api/v1/attachments", headers=FORCE_ANON_HEADERS).status_code == 200
