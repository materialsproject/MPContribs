import pytest
from beanie import PydanticObjectId

from mpcontribs_api.domains.contributions.dependencies import get_contribution_service
from mpcontribs_api.domains.contributions.models import ContributionOut
from mpcontribs_api.exceptions import ConflictError, NotFoundError
from mpcontribs_api.pagination import Page
from tests.integration.conftest import FORCE_ANON_HEADERS

# Contributions are worker-written: the router is read-only. These tests cover the GET routes and
# assert the mutating verbs are no longer mounted (405).

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def contribution_service(test_app, mock_contribution_service):
    test_app.dependency_overrides[get_contribution_service] = lambda: mock_contribution_service
    yield mock_contribution_service
    test_app.dependency_overrides.pop(get_contribution_service, None)


SAMPLE_OUT = ContributionOut(project="p", material_id="mp-1", formula="Fe2O3")


# ===========================================================================
# Read routing (GET by id, by natural identity)
# ===========================================================================


class TestContributionReadRouting:
    def test_get_by_id_conventional_path(self, client, contribution_service):
        contribution_service.read_one.return_value = SAMPLE_OUT
        assert client.get(f"/api/v1/contributions/{PydanticObjectId()}").status_code == 200

    def test_get_by_identity_defaults_unsupplied_subset(self, client, contribution_service):
        contribution_service.read_one.return_value = SAMPLE_OUT
        r = client.get("/api/v1/contributions/item?project=p&chemical_system_id=Fe-O")
        assert r.status_code == 200
        identifiers = contribution_service.read_one.await_args.args[0]
        # The literal ``item`` must reach ``read_one`` as an identity dict, not ``{"id": "item"}``.
        assert identifiers["project"] == "p"
        assert "id" not in identifiers
        # Unsupplied hierarchy/tiebreaker fields default to None; the service pins/relaxes them.
        assert identifiers["material_id"] is None
        assert identifiers["formula"] is None
        # The identity dict always carries the full natural key; an unsupplied condition_key defaults to
        # "" (matching the empty-condition row) and an unsupplied unique_value is present as None, which
        # Mongo-matches null-or-absent stored values (keep_nulls=False).
        assert identifiers["unique_value"] is None
        assert identifiers["condition_key"] == ""

    def test_get_by_identity_forwards_condition_key(self, client, contribution_service):
        contribution_service.read_one.return_value = SAMPLE_OUT
        client.get(
            "/api/v1/contributions/item",
            params={"project": "p", "chemical_system_id": "Fe-O", "condition_key": "T=300K"},
        )
        identifiers = contribution_service.read_one.await_args.args[0]
        assert identifiers["condition_key"] == "T=300K"

    def test_get_by_identity_forwards_full_subset(self, client, contribution_service):
        contribution_service.read_one.return_value = SAMPLE_OUT
        client.get(
            "/api/v1/contributions/item?project=p&chemical_system_id=Fe-O&material_id=mp-1&formula=Fe2O3&unique_value=A"
        )
        identifiers = contribution_service.read_one.await_args.args[0]
        assert identifiers["material_id"] == "mp-1"
        assert identifiers["unique_value"] == "A"

    def test_missing_required_chemical_system_returns_422(self, client, contribution_service):
        assert client.get("/api/v1/contributions/item?project=p").status_code == 422

    def test_ambiguous_identity_returns_409(self, client, contribution_service):
        contribution_service.read_one.side_effect = ConflictError("ambiguous")
        r = client.get("/api/v1/contributions/item?project=p&chemical_system_id=Fe-O")
        assert r.status_code == 409

    # A material_id without a formula violates the identifier hierarchy. ``ContributionIdentity``'s
    # model_validator rejects it at parse time (422), so the request never reaches the service.
    def test_get_by_identity_bad_hierarchy_returns_422(self, client, contribution_service):
        r = client.get("/api/v1/contributions/item?project=p&chemical_system_id=Fe-O&material_id=mp-1")
        assert r.status_code == 422
        contribution_service.read_one.assert_not_called()

    def test_get_collection_open_to_anon(self, client, contribution_service):
        contribution_service.read_many.return_value = Page(items=[], next_cursor=None)
        r = client.get("/api/v1/contributions", headers=FORCE_ANON_HEADERS)
        assert r.status_code == 200


# ===========================================================================
# GET /contributions/download/{short_mime}
# ===========================================================================


class TestDownloadContributions:
    def test_default_format_jsonl_returns_200(self, client, contribution_service):
        # The contributions route gives `format` a default of JSONL, so it works
        # with the param omitted (component routes require it — see test_component_routes).
        contribution_service.download.return_value = iter([b"x"])
        assert client.get("/api/v1/contributions/download/gz").status_code == 200

    def test_csv_format_returns_200(self, client, contribution_service):
        contribution_service.download.return_value = iter([b"x"])
        assert client.get("/api/v1/contributions/download/gz?format=csv").status_code == 200

    def test_body_is_streamed_bytes(self, client, contribution_service):
        contribution_service.download.return_value = iter([b"abc", b"def"])
        assert client.get("/api/v1/contributions/download/gz").content == b"abcdef"

    def test_invalid_short_mime_returns_422(self, client, contribution_service):
        contribution_service.download.return_value = iter([b"x"])
        # Only 'gz' is a valid ShortMimeFormat.
        assert client.get("/api/v1/contributions/download/zip").status_code == 422

    def test_invalid_format_returns_422(self, client, contribution_service):
        contribution_service.download.return_value = iter([b"x"])
        assert client.get("/api/v1/contributions/download/gz?format=xml").status_code == 422

    def test_format_forwarded_to_repo(self, client, contribution_service):
        contribution_service.download.return_value = iter([b"x"])
        client.get("/api/v1/contributions/download/gz?format=csv")
        assert contribution_service.download.call_args.kwargs["format"] == "csv"

    def test_fields_parsed_and_forwarded(self, client, contribution_service):
        contribution_service.download.return_value = iter([b"x"])
        client.get("/api/v1/contributions/download/gz?_fields=project")
        forwarded = contribution_service.download.call_args.kwargs["fields"]
        assert "project" in forwarded

    def test_invalid_fields_returns_422(self, client, contribution_service):
        contribution_service.download.return_value = iter([b"x"])
        assert client.get("/api/v1/contributions/download/gz?_fields=not_a_field").status_code == 422

    def test_filename_names_the_contributions_resource(self, client, contribution_service):
        """The attachment filename references the contributions resource."""
        contribution_service.download.return_value = iter([b"x"])
        cd = client.get("/api/v1/contributions/download/gz").headers["content-disposition"]
        assert "contributions" in cd

    def test_csv_filename_uses_csv_extension(self, client, contribution_service):
        """A CSV download is named *.csv.gz, matching the requested format."""
        contribution_service.download.return_value = iter([b"x"])
        cd = client.get("/api/v1/contributions/download/gz?format=csv").headers["content-disposition"]
        assert ".csv.gz" in cd

    def test_repo_error_surfaces_as_uniform_json(self, client, contribution_service):
        # An AppError raised while the repo builds the download surfaces through the
        # registered exception handler as the uniform error envelope (not a 500 traceback).
        contribution_service.download.side_effect = NotFoundError("nothing to download")
        r = client.get("/api/v1/contributions/download/gz")
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "not_found"


# ===========================================================================
# Mutating verbs are no longer mounted (contributions flow through /uploads)
# ===========================================================================


class TestContributionWritesRemoved:
    """Every write verb is gone from the contributions router, so the path matches a read-only route
    and FastAPI responds 405 Method Not Allowed (routing rejects it before the service is reached)."""

    def test_post_collection_405(self, client, contribution_service):
        assert client.post("/api/v1/contributions", json=[]).status_code == 405
        contribution_service.read_many.assert_not_called()

    def test_put_collection_405(self, client, contribution_service):
        assert client.put("/api/v1/contributions", json=[]).status_code == 405

    def test_patch_collection_405(self, client, contribution_service):
        assert client.patch("/api/v1/contributions", json={"is_public": True}).status_code == 405

    def test_delete_collection_405(self, client, contribution_service):
        assert client.delete("/api/v1/contributions").status_code == 405

    def test_put_by_id_405(self, client, contribution_service):
        assert client.put(f"/api/v1/contributions/{PydanticObjectId()}", json={}).status_code == 405

    def test_patch_by_id_405(self, client, contribution_service):
        assert client.patch(f"/api/v1/contributions/{PydanticObjectId()}", json={"formula": "H2O"}).status_code == 405

    def test_delete_by_id_405(self, client, contribution_service):
        assert client.delete(f"/api/v1/contributions/{PydanticObjectId()}").status_code == 405

    def test_patch_by_identity_405(self, client, contribution_service):
        r = client.patch(
            "/api/v1/contributions/item?project=p&chemical_system_id=Fe-O&material_id=mp-1&formula=Fe2O3",
            json={"is_public": True},
        )
        assert r.status_code == 405

    def test_delete_by_identity_405(self, client, contribution_service):
        r = client.delete("/api/v1/contributions/item?project=p&chemical_system_id=Fe-O&material_id=mp-1&formula=Fe2O3")
        assert r.status_code == 405
