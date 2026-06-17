from unittest.mock import AsyncMock

import pytest
from beanie import PydanticObjectId

from mpcontribs_api.domains._shared.models import ComponentDeleteResponse
from mpcontribs_api.domains.attachments.dependencies import get_attachment_service
from mpcontribs_api.domains.structures.dependencies import get_structure_service
from mpcontribs_api.domains.structures.models import StructureOut
from mpcontribs_api.domains.tables.dependencies import get_table_service
from mpcontribs_api.domains.tables.models import TableOut
from mpcontribs_api.pagination import Page

# ---------------------------------------------------------------------------
# Fixtures: every component endpoint routes through the unified ComponentService,
# so each domain has a single mock service override.
# ---------------------------------------------------------------------------


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


SAMPLE_STRUCTURE = StructureOut(name="Fe2O3.cif", md5="a" * 32)
SAMPLE_TABLE = TableOut(name="bandgaps", md5="b" * 32)


# ===========================================================================
# STRUCTURES
# ===========================================================================


class TestStructuresList:
    def test_empty_page_returns_200(self, client, structure_service):
        structure_service.get_many.return_value = Page(items=[], next_cursor=None)
        assert client.get("/api/v1/structures").status_code == 200

    def test_page_shape(self, client, structure_service):
        structure_service.get_many.return_value = Page(items=[SAMPLE_STRUCTURE], next_cursor="c")
        body = client.get("/api/v1/structures").json()
        assert "items" in body
        assert body["next_cursor"] == "c"

    def test_service_called_with_pagination(self, client, structure_service):
        structure_service.get_many.return_value = Page(items=[], next_cursor=None)
        client.get("/api/v1/structures?limit=5")
        kwargs = structure_service.get_many.call_args.kwargs
        assert kwargs["pagination"].limit == 5

    def test_invalid_fields_returns_422(self, client, structure_service):
        structure_service.get_many.return_value = Page(items=[], next_cursor=None)
        assert client.get("/api/v1/structures?_fields=not_a_field").status_code == 422

    def test_valid_fields_forwarded(self, client, structure_service):
        structure_service.get_many.return_value = Page(items=[], next_cursor=None)
        client.get("/api/v1/structures?_fields=name")
        # parse_fields always includes the id identity field.
        assert structure_service.get_many.call_args.kwargs["fields"] == frozenset({"id", "name"})


class TestStructuresDelete:
    def test_batch_delete_returns_200(self, client, structure_service):
        structure_service.delete.return_value = ComponentDeleteResponse(num_deleted=3)
        r = client.delete("/api/v1/structures")
        assert r.status_code == 200
        assert r.json() == {"num_deleted": 3, "num_skipped": 0, "referenced_ids": []}

    def test_service_delete_called(self, client, structure_service):
        structure_service.delete.return_value = ComponentDeleteResponse(num_deleted=0)
        client.delete("/api/v1/structures")
        structure_service.delete.assert_awaited_once()


class TestStructuresInsert:
    def test_post_route_exists(self, client, structure_service):
        # Empty body -> handler invoked; service returns a summary-shaped object.
        structure_service.insert.return_value = {"total": 0, "succeeded": [], "failed": []}
        r = client.post("/api/v1/structures", json=[])
        assert r.status_code != 404

    def test_post_forwards_to_service(self, client, structure_service):
        structure_service.insert.return_value = {"total": 0, "succeeded": [], "failed": []}
        client.post("/api/v1/structures", json=[])
        structure_service.insert.assert_awaited_once()


class TestStructuresByIdRouting:
    def test_get_by_id_conventional_path(self, client, structure_service):
        structure_service.get_by_id.return_value = SAMPLE_STRUCTURE
        assert client.get(f"/api/v1/structures/{PydanticObjectId()}").status_code == 200

    def test_delete_by_id_conventional_path(self, client, structure_service):
        structure_service.delete_by_id.return_value = ComponentDeleteResponse(num_deleted=1)
        assert client.delete(f"/api/v1/structures/{PydanticObjectId()}").status_code == 200

    def test_patch_by_id_conventional_path(self, client, structure_service):
        structure_service.patch_by_id.return_value = SAMPLE_STRUCTURE
        r = client.patch(f"/api/v1/structures/{PydanticObjectId()}", json={"name": "renamed"})
        assert r.status_code == 200

    def test_download_conventional_path(self, client, structure_service):
        structure_service.download.return_value = iter([b"x"])
        assert client.get("/api/v1/structures/download/gz?format=csv").status_code == 200


# ===========================================================================
# TABLES
# ===========================================================================


class TestTablesList:
    def test_empty_page_returns_200(self, client, table_service):
        table_service.get_many.return_value = Page(items=[], next_cursor=None)
        assert client.get("/api/v1/tables").status_code == 200

    def test_page_shape(self, client, table_service):
        table_service.get_many.return_value = Page(items=[SAMPLE_TABLE], next_cursor=None)
        assert "items" in client.get("/api/v1/tables").json()

    def test_invalid_fields_returns_422(self, client, table_service):
        table_service.get_many.return_value = Page(items=[], next_cursor=None)
        assert client.get("/api/v1/tables?_fields=nope").status_code == 422

    def test_default_fields_accepted(self, client, table_service):
        table_service.get_many.return_value = Page(items=[], next_cursor=None)
        assert client.get("/api/v1/tables").status_code == 200


class TestTablesDelete:
    def test_batch_delete_returns_200(self, client, table_service):
        table_service.delete.return_value = ComponentDeleteResponse(num_deleted=2)
        assert client.delete("/api/v1/tables").json() == {
            "num_deleted": 2,
            "num_skipped": 0,
            "referenced_ids": [],
        }


class TestTablesInsert:
    def test_post_forwards_to_service(self, client, table_service):
        table_service.insert.return_value = {"total": 0, "succeeded": [], "failed": []}
        client.post("/api/v1/tables", json=[])
        table_service.insert.assert_awaited_once()


class TestTablesByIdRouting:
    def test_get_by_id_conventional_path(self, client, table_service):
        table_service.get_by_id.return_value = SAMPLE_TABLE
        assert client.get(f"/api/v1/tables/{PydanticObjectId()}").status_code == 200

    def test_delete_by_id_conventional_path(self, client, table_service):
        table_service.delete_by_id.return_value = ComponentDeleteResponse(num_deleted=1)
        assert client.delete(f"/api/v1/tables/{PydanticObjectId()}").status_code == 200

    def test_patch_by_id_conventional_path(self, client, table_service):
        table_service.patch_by_id.return_value = SAMPLE_TABLE
        r = client.patch(f"/api/v1/tables/{PydanticObjectId()}", json={"name": "x"})
        assert r.status_code == 200


# ===========================================================================
# ATTACHMENTS
# ===========================================================================


class TestAttachmentsRouterWiring:
    def test_list_calls_attachment_service(self, client, attachment_service):
        attachment_service.get_many.return_value = Page(items=[], next_cursor=None)
        r = client.get("/api/v1/attachments")
        assert r.status_code == 200
        attachment_service.get_many.assert_awaited_once()

    def test_get_by_id_calls_attachment_service(self, client, attachment_service):
        attachment_service.get_by_id.return_value = None
        client.get(f"/api/v1/attachments/{PydanticObjectId()}")
        attachment_service.get_by_id.assert_awaited_once()

    def test_delete_by_id_calls_attachment_service(self, client, attachment_service):
        attachment_service.delete_by_id.return_value = ComponentDeleteResponse(num_deleted=1)
        client.delete(f"/api/v1/attachments/{PydanticObjectId()}")
        attachment_service.delete_by_id.assert_awaited_once()

    def test_batch_delete_calls_attachment_service(self, client, attachment_service):
        attachment_service.delete.return_value = ComponentDeleteResponse(num_deleted=0)
        client.delete("/api/v1/attachments")
        attachment_service.delete.assert_awaited_once()


# ===========================================================================
# Component downloads: /{resource}/download/{short_mime}
#
# Parametrised over the three component resources so download behavior is held
# to the same contract everywhere.  Each entry is
# (url_prefix, service_fixture_name, expected_stem).
# ===========================================================================

_DOWNLOAD_CASES = [
    ("structures", "structure_service", "structures"),
    ("tables", "table_service", "tables"),
    ("attachments", "attachment_service", "attachments"),
]


@pytest.fixture
def download_target(request):
    """Resolve a (prefix, service_fixture, stem) case into a wired service mock."""
    prefix, service_fixture, stem = request.param
    service = request.getfixturevalue(service_fixture)
    service.download.return_value = iter([b"x"])
    return prefix, service, stem


@pytest.mark.parametrize("download_target", _DOWNLOAD_CASES, indirect=True)
class TestComponentDownloads:
    def test_csv_returns_200(self, client, download_target):
        prefix, *_ = download_target
        assert client.get(f"/api/v1/{prefix}/download/gz?format=csv").status_code == 200

    def test_jsonl_returns_200(self, client, download_target):
        prefix, *_ = download_target
        assert client.get(f"/api/v1/{prefix}/download/gz?format=jsonl").status_code == 200

    def test_body_is_streamed_bytes(self, client, download_target):
        prefix, service, _ = download_target
        service.download.return_value = iter([b"ab", b"cd"])
        assert client.get(f"/api/v1/{prefix}/download/gz?format=jsonl").content == b"abcd"

    def test_format_is_required(self, client, download_target):
        # Component download routes give `format` no default, unlike contributions.
        prefix, *_ = download_target
        assert client.get(f"/api/v1/{prefix}/download/gz").status_code == 422

    def test_invalid_short_mime_returns_422(self, client, download_target):
        prefix, *_ = download_target
        assert client.get(f"/api/v1/{prefix}/download/zip?format=jsonl").status_code == 422

    def test_invalid_format_returns_422(self, client, download_target):
        prefix, *_ = download_target
        assert client.get(f"/api/v1/{prefix}/download/gz?format=xml").status_code == 422

    def test_format_forwarded_to_service(self, client, download_target):
        prefix, service, _ = download_target
        client.get(f"/api/v1/{prefix}/download/gz?format=csv")
        assert service.download.call_args.kwargs["format"] == "csv"

    def test_csv_filename_uses_csv_extension(self, client, download_target):
        """A CSV download is named *.csv.gz, matching the requested format."""
        prefix, *_ = download_target
        cd = client.get(f"/api/v1/{prefix}/download/gz?format=csv").headers["content-disposition"]
        assert ".csv.gz" in cd
