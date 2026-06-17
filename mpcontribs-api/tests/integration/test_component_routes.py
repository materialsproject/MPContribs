from unittest.mock import AsyncMock

import pytest
from beanie import PydanticObjectId

from mpcontribs_api.domains._shared.models import ComponentDeleteResponse
from mpcontribs_api.domains.attachments.dependencies import get_attachment_service, get_scoped_attachments
from mpcontribs_api.domains.structures.dependencies import get_scoped_tables as get_scoped_structures
from mpcontribs_api.domains.structures.dependencies import get_structure_service
from mpcontribs_api.domains.structures.models import StructureOut
from mpcontribs_api.domains.tables.dependencies import get_scoped_tables, get_table_service
from mpcontribs_api.domains.tables.models import TableOut
from mpcontribs_api.pagination import Page

# ---------------------------------------------------------------------------
# Fixtures: inject mock repos per domain
# ---------------------------------------------------------------------------


@pytest.fixture
def structure_repo(test_app, mock_structure_repo):
    test_app.dependency_overrides[get_scoped_structures] = lambda: mock_structure_repo
    yield mock_structure_repo
    test_app.dependency_overrides.pop(get_scoped_structures, None)


@pytest.fixture
def table_repo(test_app, mock_table_repo):
    test_app.dependency_overrides[get_scoped_tables] = lambda: mock_table_repo
    yield mock_table_repo
    test_app.dependency_overrides.pop(get_scoped_tables, None)


@pytest.fixture
def attachment_repo(test_app, mock_attachment_repo):
    test_app.dependency_overrides[get_scoped_attachments] = lambda: mock_attachment_repo
    yield mock_attachment_repo
    test_app.dependency_overrides.pop(get_scoped_attachments, None)


# Delete endpoints route through the component service (not the repo), so they are
# overridden separately from the read/insert/patch endpoints above.
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
    def test_empty_page_returns_200(self, client, structure_repo):
        structure_repo.get_structures.return_value = Page(items=[], next_cursor=None)
        assert client.get("/api/v1/structures").status_code == 200

    def test_page_shape(self, client, structure_repo):
        structure_repo.get_structures.return_value = Page(items=[SAMPLE_STRUCTURE], next_cursor="c")
        body = client.get("/api/v1/structures").json()
        assert "items" in body
        assert body["next_cursor"] == "c"

    def test_repo_called_with_pagination(self, client, structure_repo):
        structure_repo.get_structures.return_value = Page(items=[], next_cursor=None)
        client.get("/api/v1/structures?limit=5")
        kwargs = structure_repo.get_structures.call_args.kwargs
        assert kwargs["pagination"].limit == 5

    def test_invalid_fields_returns_422(self, client, structure_repo):
        structure_repo.get_structures.return_value = Page(items=[], next_cursor=None)
        assert client.get("/api/v1/structures?_fields=not_a_field").status_code == 422

    def test_valid_fields_forwarded(self, client, structure_repo):
        structure_repo.get_structures.return_value = Page(items=[], next_cursor=None)
        client.get("/api/v1/structures?_fields=name")
        # parse_fields always includes the id identity field.
        assert structure_repo.get_structures.call_args.kwargs["fields"] == frozenset({"id", "name"})


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
    def test_post_route_exists(self, client, structure_repo):
        # Empty body -> handler invoked; repo returns a summary-shaped object.
        structure_repo.insert_structures.return_value = {"total": 0, "succeeded": [], "failed": []}
        r = client.post("/api/v1/structures", json=[])
        assert r.status_code != 404

    def test_post_forwards_to_repo(self, client, structure_repo):
        structure_repo.insert_structures.return_value = {"total": 0, "succeeded": [], "failed": []}
        client.post("/api/v1/structures", json=[])
        structure_repo.insert_structures.assert_awaited_once()


class TestStructuresByIdRouting:
    def test_get_by_id_conventional_path(self, client, structure_repo):
        structure_repo.get_structure_by_id.return_value = SAMPLE_STRUCTURE
        assert client.get(f"/api/v1/structures/{PydanticObjectId()}").status_code == 200

    def test_delete_by_id_conventional_path(self, client, structure_service):
        structure_service.delete_by_id.return_value = ComponentDeleteResponse(num_deleted=1)
        assert client.delete(f"/api/v1/structures/{PydanticObjectId()}").status_code == 200

    def test_patch_by_id_conventional_path(self, client, structure_repo):
        structure_repo.patch_structure_by_id.return_value = SAMPLE_STRUCTURE
        r = client.patch(f"/api/v1/structures/{PydanticObjectId()}", json={"name": "renamed"})
        assert r.status_code == 200

    def test_download_conventional_path(self, client, structure_repo):
        structure_repo.download_structures.return_value = iter([b"x"])
        assert client.get("/api/v1/structures/download/gz?format=csv").status_code == 200


# ===========================================================================
# TABLES
# ===========================================================================


class TestTablesList:
    def test_empty_page_returns_200(self, client, table_repo):
        table_repo.get_tables.return_value = Page(items=[], next_cursor=None)
        assert client.get("/api/v1/tables").status_code == 200

    def test_page_shape(self, client, table_repo):
        table_repo.get_tables.return_value = Page(items=[SAMPLE_TABLE], next_cursor=None)
        assert "items" in client.get("/api/v1/tables").json()

    def test_invalid_fields_returns_422(self, client, table_repo):
        table_repo.get_tables.return_value = Page(items=[], next_cursor=None)
        assert client.get("/api/v1/tables?_fields=nope").status_code == 422

    def test_default_fields_accepted(self, client, table_repo):
        table_repo.get_tables.return_value = Page(items=[], next_cursor=None)
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
    def test_post_forwards_to_repo(self, client, table_repo):
        table_repo.insert_tables.return_value = {"total": 0, "succeeded": [], "failed": []}
        client.post("/api/v1/tables", json=[])
        table_repo.insert_tables.assert_awaited_once()


class TestTablesByIdRouting:
    def test_get_by_id_conventional_path(self, client, table_repo):
        table_repo.get_table_by_id.return_value = SAMPLE_TABLE
        assert client.get(f"/api/v1/tables/{PydanticObjectId()}").status_code == 200

    def test_delete_by_id_conventional_path(self, client, table_service):
        table_service.delete_by_id.return_value = ComponentDeleteResponse(num_deleted=1)
        assert client.delete(f"/api/v1/tables/{PydanticObjectId()}").status_code == 200

    def test_patch_by_id_conventional_path(self, client, table_repo):
        table_repo.patch_table_by_id.return_value = SAMPLE_TABLE
        r = client.patch(f"/api/v1/tables/{PydanticObjectId()}", json={"name": "x"})
        assert r.status_code == 200


# ===========================================================================
# ATTACHMENTS  (RED: router is a copy of structures, wrong repo + methods)
# ===========================================================================


class TestAttachmentsRouterWiring:
    def test_list_calls_attachment_repo(self, client, attachment_repo):
        attachment_repo.get_attachments.return_value = Page(items=[], next_cursor=None)
        r = client.get("/api/v1/attachments")
        assert r.status_code == 200
        attachment_repo.get_attachments.assert_awaited_once()

    def test_get_by_id_calls_attachment_repo(self, client, attachment_repo):
        attachment_repo.get_attachment_by_id.return_value = None
        client.get(f"/api/v1/attachments/{PydanticObjectId()}")
        attachment_repo.get_attachment_by_id.assert_awaited_once()

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
# (url_prefix, repo_fixture_name, download_method, expected_stem).
# ===========================================================================

_DOWNLOAD_CASES = [
    ("structures", "structure_repo", "download_structures", "structures"),
    ("tables", "table_repo", "download_tables", "tables"),
    ("attachments", "attachment_repo", "download_attachments", "attachments"),
]


@pytest.fixture
def download_target(request):
    """Resolve a (prefix, repo, method_name, stem) case into a wired repo mock."""
    prefix, repo_fixture, method, stem = request.param
    repo = request.getfixturevalue(repo_fixture)
    getattr(repo, method).return_value = iter([b"x"])
    return prefix, repo, method, stem


@pytest.mark.parametrize("download_target", _DOWNLOAD_CASES, indirect=True)
class TestComponentDownloads:
    def test_csv_returns_200(self, client, download_target):
        prefix, *_ = download_target
        assert client.get(f"/api/v1/{prefix}/download/gz?format=csv").status_code == 200

    def test_jsonl_returns_200(self, client, download_target):
        prefix, *_ = download_target
        assert client.get(f"/api/v1/{prefix}/download/gz?format=jsonl").status_code == 200

    def test_body_is_streamed_bytes(self, client, download_target):
        prefix, repo, method, _ = download_target
        getattr(repo, method).return_value = iter([b"ab", b"cd"])
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

    def test_format_forwarded_to_repo(self, client, download_target):
        prefix, repo, method, _ = download_target
        client.get(f"/api/v1/{prefix}/download/gz?format=csv")
        assert getattr(repo, method).call_args.kwargs["format"] == "csv"

    def test_csv_filename_uses_csv_extension(self, client, download_target):
        """A CSV download is named *.csv.gz, matching the requested format."""
        prefix, *_ = download_target
        cd = client.get(f"/api/v1/{prefix}/download/gz?format=csv").headers["content-disposition"]
        assert ".csv.gz" in cd
