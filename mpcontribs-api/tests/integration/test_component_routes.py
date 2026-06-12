"""Integration tests for component routers: /structures, /tables, /attachments.

All use AsyncMock repositories via dependency_overrides, so no DB is required —
the same pattern as test_projects.py / test_contributions.py.

THREE BUG CLASSES ARE PINNED TO INTENDED BEHAVIOR (these tests are RED):
"""

import pytest
from beanie import PydanticObjectId

from mpcontribs_api.domains._shared.models import DeleteResponse
from mpcontribs_api.domains.attachments.dependencies import get_scoped_attachments
from mpcontribs_api.domains.structures.dependencies import get_scoped_tables as get_scoped_structures
from mpcontribs_api.domains.structures.models import StructureOut
from mpcontribs_api.domains.tables.dependencies import get_scoped_tables
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
    def test_batch_delete_returns_200(self, client, structure_repo):
        structure_repo.delete_structures.return_value = DeleteResponse(num_deleted=3)
        r = client.delete("/api/v1/structures")
        assert r.status_code == 200
        assert r.json() == {"num_deleted": 3}

    def test_repo_delete_called(self, client, structure_repo):
        structure_repo.delete_structures.return_value = DeleteResponse(num_deleted=0)
        client.delete("/api/v1/structures")
        structure_repo.delete_structures.assert_awaited_once()


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

    def test_delete_by_id_conventional_path(self, client, structure_repo):
        structure_repo.delete_structure_by_id.return_value = DeleteResponse(num_deleted=1)
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
    def test_batch_delete_returns_200(self, client, table_repo):
        table_repo.delete_tables.return_value = DeleteResponse(num_deleted=2)
        assert client.delete("/api/v1/tables").json() == {"num_deleted": 2}


class TestTablesInsert:
    def test_post_forwards_to_repo(self, client, table_repo):
        table_repo.insert_tables.return_value = {"total": 0, "succeeded": [], "failed": []}
        client.post("/api/v1/tables", json=[])
        table_repo.insert_tables.assert_awaited_once()


class TestTablesByIdRouting:
    """RED: same glued-path bug as structures."""

    def test_get_by_id_conventional_path(self, client, table_repo):
        table_repo.get_table_by_id.return_value = SAMPLE_TABLE
        assert client.get(f"/api/v1/tables/{PydanticObjectId()}").status_code == 200

    def test_delete_by_id_conventional_path(self, client, table_repo):
        table_repo.delete_table_by_id.return_value = DeleteResponse(num_deleted=1)
        assert client.delete(f"/api/v1/tables/{PydanticObjectId()}").status_code == 200

    def test_patch_by_id_conventional_path(self, client, table_repo):
        table_repo.patch_table_by_id.return_value = SAMPLE_TABLE
        r = client.patch(f"/api/v1/tables/{PydanticObjectId()}", json={"name": "x"})
        assert r.status_code == 200


# ===========================================================================
# ATTACHMENTS  (RED: router is a copy of structures, wrong repo + methods)
# ===========================================================================


class TestAttachmentsRouterWiring:
    """RED: attachments/router.py wires StructureDep and calls structure repo
    methods. With the attachment repo overridden, the structure-named methods
    don't exist on it, so these assertions can't pass until the router is
    rewritten against the attachment domain.
    """

    def test_list_calls_attachment_repo(self, client, attachment_repo):
        attachment_repo.get_attachments.return_value = Page(items=[], next_cursor=None)
        r = client.get("/api/v1/attachments")
        assert r.status_code == 200
        attachment_repo.get_attachments.assert_awaited_once()

    def test_get_by_id_calls_attachment_repo(self, client, attachment_repo):
        attachment_repo.get_attachment_by_id.return_value = None
        client.get(f"/api/v1/attachments/{PydanticObjectId()}")
        attachment_repo.get_attachment_by_id.assert_awaited_once()

    def test_delete_by_id_calls_attachment_repo(self, client, attachment_repo):
        attachment_repo.delete_attachment_by_id.return_value = DeleteResponse(num_deleted=1)
        client.delete(f"/api/v1/attachments/{PydanticObjectId()}")
        attachment_repo.delete_attachment_by_id.assert_awaited_once()

    def test_batch_delete_calls_attachment_repo(self, client, attachment_repo):
        attachment_repo.delete_attachments.return_value = DeleteResponse(num_deleted=0)
        client.delete("/api/v1/attachments")
        attachment_repo.delete_attachments.assert_awaited_once()
