import pytest
from beanie import PydanticObjectId

from mpcontribs_api.domains._shared.bulk import BulkDeleteSummary, BulkUpdateSummary, BulkWriteSummary
from mpcontribs_api.domains.contributions.dependencies import get_contribution_service
from mpcontribs_api.domains.contributions.models import ContributionOut
from mpcontribs_api.exceptions import ConflictError, NotFoundError
from tests.integration.conftest import AUTHED_HEADERS, FORCE_ANON_HEADERS

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _authenticate(client):
    """Mutating contribution endpoints now require an authenticated caller.

    Default the shared client to an authenticated identity so the existing
    mutation tests still exercise the handler; anonymous-rejection is covered
    explicitly by TestContributionMutationsRequireAuth via FORCE_ANON_HEADERS.
    """
    client.headers.update(AUTHED_HEADERS)


@pytest.fixture
def contribution_service(test_app, mock_contribution_service):
    test_app.dependency_overrides[get_contribution_service] = lambda: mock_contribution_service
    yield mock_contribution_service
    test_app.dependency_overrides.pop(get_contribution_service, None)


def _valid_contribution_body(**overrides) -> dict:
    # ContributionIn inherits a required _id from BaseDocumentWithInput, so a
    # client-supplied object id is part of the create contract (mirrors the
    # service unit tests, which always pass _id).
    body = {
        "_id": str(PydanticObjectId()),
        "project": "test-project",
        "material_id": "mp-1234",
        "chemical_system_id": "Fe-O",
        "formula": "Fe2O3",
        "data": {"bandGap": 2.1},
    }
    body.update(overrides)
    return body


SAMPLE_OUT = ContributionOut(project="p", material_id="mp-1", formula="Fe2O3")


# ===========================================================================
# POST /contributions  (bulk insert via service)
# ===========================================================================


class TestInsertContributions:
    def test_empty_list_returns_200(self, client, contribution_service):
        contribution_service.insert_many.return_value = BulkWriteSummary(
            total=0, succeeded=[], failed=[]
        )
        r = client.post("/api/v1/contributions", json=[])
        assert r.status_code == 200

    def test_response_has_summary_shape(self, client, contribution_service):
        contribution_service.insert_many.return_value = BulkWriteSummary(
            total=0, succeeded=[], failed=[]
        )
        body = client.post("/api/v1/contributions", json=[]).json()
        assert set(body) == {"total", "succeeded", "failed"}

    def test_service_receives_parsed_contributions(self, client, contribution_service):
        contribution_service.insert_many.return_value = BulkWriteSummary(
            total=1, succeeded=[], failed=[]
        )
        client.post("/api/v1/contributions", json=[_valid_contribution_body()])
        contributions = contribution_service.insert_many.call_args.kwargs["contributions"]
        assert len(contributions) == 1
        assert contributions[0].project == "test-project"

    def test_malformed_body_returns_422(self, client, contribution_service):
        # Missing required 'formula'.
        r = client.post(
            "/api/v1/contributions",
            json=[{"_id": str(PydanticObjectId()), "project": "p", "material_id": "mp-1"}],
        )
        assert r.status_code == 422
        contribution_service.insert_many.assert_not_called()

    def test_non_list_body_returns_422(self, client, contribution_service):
        r = client.post("/api/v1/contributions", json=_valid_contribution_body())
        assert r.status_code == 422


# ===========================================================================
# PUT /contributions  (bulk upsert via service)
# ===========================================================================


class TestUpsertContributions:
    def test_empty_list_returns_200(self, client, contribution_service):
        contribution_service.upsert_many.return_value = BulkWriteSummary(total=0, succeeded=[], failed=[])
        r = client.put("/api/v1/contributions", json=[])
        assert r.status_code == 200
        assert set(r.json()) == {"total", "succeeded", "failed"}

    def test_service_receives_parsed_contributions(self, client, contribution_service):
        contribution_service.upsert_many.return_value = BulkWriteSummary(total=1, succeeded=[], failed=[])
        client.put("/api/v1/contributions", json=[_valid_contribution_body()])
        contributions = contribution_service.upsert_many.call_args.kwargs["contributions"]
        assert contributions[0].material_id == "mp-1234"

    def test_malformed_body_returns_422(self, client, contribution_service):
        r = client.put(
            "/api/v1/contributions",
            json=[{"_id": str(PydanticObjectId()), "project": "p"}],
        )
        assert r.status_code == 422
        contribution_service.upsert_many.assert_not_called()


# ===========================================================================
# Single-resource routes  (RED: glued path params)
# ===========================================================================


class TestContributionByIdRouting:
    """RED: routes mount as /contributions{id} not /contributions/{id}."""

    def test_get_by_id_conventional_path(self, client, contribution_service):
        contribution_service.read_one.return_value = SAMPLE_OUT
        assert client.get(f"/api/v1/contributions/{PydanticObjectId()}").status_code == 200

    def test_patch_by_id_conventional_path(self, client, contribution_service):
        contribution_service.update_one.return_value = SAMPLE_OUT
        r = client.patch(f"/api/v1/contributions/{PydanticObjectId()}", json={"formula": "H2O"})
        assert r.status_code == 200

    def test_put_by_id_conventional_path(self, client, contribution_service):
        contribution_service.upsert_one.return_value = SAMPLE_OUT
        r = client.put(f"/api/v1/contributions/{PydanticObjectId()}", json=_valid_contribution_body())
        assert r.status_code == 200

    def test_delete_by_id_conventional_path(self, client, contribution_service):
        contribution_service.delete_one.return_value = BulkDeleteSummary(num_deleted=1, num_children_deleted=0)
        assert client.delete(f"/api/v1/contributions/{PydanticObjectId()}").status_code == 200

    def test_download_route_conventional_path(self, client, contribution_service):
        contribution_service.download.return_value = iter([b"x"])
        assert client.get("/api/v1/contributions/download/gz").status_code == 200


class TestContributionByIdentityRouting:
    """The ``/item`` path addresses a contribution by its user-suppliable natural identity; both it and
    ``/{id}`` funnel through the unified ``read_one``/``delete_one``/``update_one`` (which take an
    identity or an id, preferring the id). The server resolves the rest and 409s on an ambiguous subset."""

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
        # Mongo-matches null-or-absent stored values (keep_nulls=False) and satisfies the repository's
        # exact-identifier-key check.
        assert identifiers["unique_value"] is None
        assert identifiers["condition_key"] == ""

    def test_get_by_identity_forwards_condition_key(self, client, contribution_service):
        contribution_service.read_one.return_value = SAMPLE_OUT
        client.get(
            "/api/v1/contributions/item",
            params={"project": "p", "chemical_system_id": "Fe-O", "condition_key": "T=300K"},
        )
        identifiers = contribution_service.read_one.await_args.args[0]
        # condition_key is a caller-suppliable selector for a specific pivoted row (no longer forced to
        # ""), so the caller's value reaches the service verbatim to address that row.
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

    def test_delete_by_identity_forwards_to_service(self, client, contribution_service):
        contribution_service.delete_one.return_value = BulkDeleteSummary(num_deleted=1, num_children_deleted=0)
        r = client.delete("/api/v1/contributions/item?project=p&chemical_system_id=Fe-O&material_id=mp-1&formula=Fe2O3")
        assert r.status_code == 200
        identifiers = contribution_service.delete_one.await_args.args[0]
        assert identifiers["project"] == "p"
        assert "id" not in identifiers

    def test_patch_by_identity_forwards_to_service(self, client, contribution_service):
        contribution_service.update_one.return_value = SAMPLE_OUT
        r = client.patch(
            "/api/v1/contributions/item?project=p&chemical_system_id=Fe-O&material_id=mp-1&formula=Fe2O3",
            json={"is_public": True},
        )
        assert r.status_code == 200
        identifiers = contribution_service.update_one.await_args.args[0]
        assert identifiers["project"] == "p"
        assert "id" not in identifiers

    # A material_id without a formula violates the identifier hierarchy. ``ContributionIdentity``'s
    # model_validator rejects it at parse time (422) for every verb, so the request never reaches the
    # service — DELETE in particular must not silently fall through to a 0-count delete.
    def test_get_by_identity_bad_hierarchy_returns_422(self, client, contribution_service):
        r = client.get("/api/v1/contributions/item?project=p&chemical_system_id=Fe-O&material_id=mp-1")
        assert r.status_code == 422
        contribution_service.read_one.assert_not_called()

    def test_delete_by_identity_bad_hierarchy_returns_422(self, client, contribution_service):
        r = client.delete("/api/v1/contributions/item?project=p&chemical_system_id=Fe-O&material_id=mp-1")
        assert r.status_code == 422
        contribution_service.delete_one.assert_not_called()

    def test_patch_by_identity_bad_hierarchy_returns_422(self, client, contribution_service):
        r = client.patch(
            "/api/v1/contributions/item?project=p&chemical_system_id=Fe-O&material_id=mp-1",
            json={"is_public": True},
        )
        assert r.status_code == 422
        contribution_service.update_one.assert_not_called()


# ===========================================================================
# Single-resource behavior (independent of the routing bug, via current paths)
# ===========================================================================


class TestDeleteContributionByIdWiring:
    def test_delete_delegates_to_service(self, client, contribution_service):
        contribution_service.delete_one.return_value = BulkDeleteSummary(num_deleted=1, num_children_deleted=2)
        oid = PydanticObjectId()
        r = client.delete(f"/api/v1/contributions/{oid}")
        assert r.status_code == 200
        contribution_service.delete_one.assert_awaited_once()

    def test_delete_passes_id_identifiers_to_service(self, client, contribution_service):
        contribution_service.delete_one.return_value = BulkDeleteSummary(num_deleted=1, num_children_deleted=0)
        oid = PydanticObjectId()
        client.delete(f"/api/v1/contributions/{oid}")
        assert contribution_service.delete_one.call_args.args[0] == {"id": str(oid)}


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


# ---------------------------------------------------------------------------
# Authentication enforcement: contribution mutations require an authenticated user
# ---------------------------------------------------------------------------


class TestBulkUpdateContributions:
    def test_publish_returns_200_and_summary(self, client, contribution_service):
        contribution_service.update_many.return_value = BulkUpdateSummary(matched=3, modified=2, projects=["mp-team"])
        r = client.patch("/api/v1/contributions", json={"is_public": True})
        assert r.status_code == 200
        assert r.json() == {"matched": 3, "modified": 2, "projects": ["mp-team"], "failed": []}

    def test_forwards_update_and_filter(self, client, contribution_service):
        from mpcontribs_api.domains.contributions.models import ContributionFilter

        contribution_service.update_many.return_value = BulkUpdateSummary(matched=0, modified=0, projects=[])
        client.patch("/api/v1/contributions?project=mp-team", json={"is_public": True})
        contribution_service.update_many.assert_awaited_once()
        kwargs = contribution_service.update_many.call_args.kwargs
        assert kwargs["update"].is_public is True
        assert isinstance(kwargs["filter"], ContributionFilter)

    def test_forwards_full_patch_body(self, client, contribution_service):
        # The bulk patch now accepts the same fields as the single-item patch (not just is_public).
        contribution_service.update_many.return_value = BulkUpdateSummary(matched=1, modified=1, projects=["mp-team"])
        r = client.patch("/api/v1/contributions", json={"formula": "Fe2O3", "data": {"y": 9.0}})
        assert r.status_code == 200
        update = contribution_service.update_many.call_args.kwargs["update"]
        assert update.formula == "Fe2O3"
        assert update.data == {"y": 9.0}

    def test_empty_patch_is_accepted_as_noop(self, client, contribution_service):
        # An empty patch is a valid no-op (parity with the single-item patch), no longer a 422.
        contribution_service.update_many.return_value = BulkUpdateSummary(matched=0, modified=0, projects=[])
        r = client.patch("/api/v1/contributions", json={})
        assert r.status_code == 200
        contribution_service.update_many.assert_awaited_once()

    def test_replace_data_query_param_forwarded(self, client, contribution_service):
        # ?replace_data=true opts a data patch out of the additive-merge default (whole-dict overwrite).
        contribution_service.update_many.return_value = BulkUpdateSummary(matched=0, modified=0, projects=[])
        client.patch("/api/v1/contributions?replace_data=true", json={"data": {"y": 9.0}})
        assert contribution_service.update_many.call_args.kwargs["replace_data"] is True

    def test_replace_data_defaults_to_false(self, client, contribution_service):
        # Omitting the flag keeps the additive-merge default.
        contribution_service.update_many.return_value = BulkUpdateSummary(matched=0, modified=0, projects=[])
        client.patch("/api/v1/contributions", json={"data": {"y": 9.0}})
        assert contribution_service.update_many.call_args.kwargs["replace_data"] is False

    def test_patch_by_id_forwards_is_public(self, client, contribution_service):
        # The single-contribution publish path: {"is_public": true} reaches the service patch.
        contribution_service.update_one.return_value = SAMPLE_OUT
        r = client.patch(f"/api/v1/contributions/{PydanticObjectId()}", json={"is_public": True})
        assert r.status_code == 200
        update = contribution_service.update_one.call_args.kwargs["update"]
        assert update.is_public is True

    def test_patch_by_id_forwards_replace_data(self, client, contribution_service):
        # The single-item path exposes the same overwrite opt-out as the bulk path.
        contribution_service.update_one.return_value = SAMPLE_OUT
        r = client.patch(
            f"/api/v1/contributions/{PydanticObjectId()}?replace_data=true", json={"data": {"y": 9.0}}
        )
        assert r.status_code == 200
        assert contribution_service.update_one.call_args.kwargs["replace_data"] is True


class TestContributionMutationsRequireAuth:
    def test_post_anon_401(self, client, contribution_service):
        r = client.post("/api/v1/contributions", json=[], headers=FORCE_ANON_HEADERS)
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "authentication_error"
        contribution_service.insert_many.assert_not_called()

    def test_put_collection_anon_401(self, client, contribution_service):
        r = client.put("/api/v1/contributions", json=[], headers=FORCE_ANON_HEADERS)
        assert r.status_code == 401
        contribution_service.upsert_many.assert_not_called()

    def test_delete_collection_anon_401(self, client, contribution_service):
        r = client.delete("/api/v1/contributions", headers=FORCE_ANON_HEADERS)
        assert r.status_code == 401
        contribution_service.delete_many.assert_not_called()

    def test_patch_collection_anon_401(self, client, contribution_service):
        r = client.patch("/api/v1/contributions", json={"is_public": True}, headers=FORCE_ANON_HEADERS)
        assert r.status_code == 401
        contribution_service.update_many.assert_not_called()

    def test_delete_by_id_anon_401(self, client, contribution_service):
        r = client.delete(f"/api/v1/contributions/{PydanticObjectId()}", headers=FORCE_ANON_HEADERS)
        assert r.status_code == 401

    def test_put_by_id_anon_401(self, client, contribution_service):
        r = client.put(
            f"/api/v1/contributions/{PydanticObjectId()}",
            json=_valid_contribution_body(),
            headers=FORCE_ANON_HEADERS,
        )
        assert r.status_code == 401
        contribution_service.upsert_one.assert_not_called()

    def test_patch_by_id_anon_401(self, client, contribution_service):
        r = client.patch(
            f"/api/v1/contributions/{PydanticObjectId()}", json={"formula": "H2O"}, headers=FORCE_ANON_HEADERS
        )
        assert r.status_code == 401
        contribution_service.update_one.assert_not_called()

    def test_get_collection_still_open_to_anon(self, client, contribution_service):
        from mpcontribs_api.pagination import Page

        contribution_service.read_many.return_value = Page(items=[], next_cursor=None)
        r = client.get("/api/v1/contributions", headers=FORCE_ANON_HEADERS)
        assert r.status_code == 200
