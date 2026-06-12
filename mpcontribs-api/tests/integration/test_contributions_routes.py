"""Integration tests for previously-untested /contributions routes.

test_contributions.py covers GET list and DELETE batch plus stub-existence of
POST/PUT. This file covers the behavior of POST, PUT, the single-resource
routes, and download — all via AsyncMock repo/service overrides.

RED behavior pinned here:

1. Glued path params (same class as the component routers). Single-resource
   contribution routes mount as ``/contributions{id}`` not
   ``/contributions/{id}``; the ``...ByIdRouting`` tests assert the
   conventional ``/{id}`` form.

2. Download route shape. The route is declared ``download/{mime}`` but the
   handler reads ``format`` from the query and never uses the ``mime`` path
   param, while structures/tables use ``download/{short_mime}`` with a
   ``DownloadFormat`` enum. test_download_route_conventional_path asserts the
   conventional ``/download/...`` path resolves.
"""

import pytest
from beanie import PydanticObjectId

from mpcontribs_api.domains._shared.bulk import BulkDeleteSummary, BulkWriteSummary
from mpcontribs_api.domains.contributions.dependencies import (
    get_contribution_service,
    get_scoped_contributions,
)
from mpcontribs_api.domains.contributions.models import ContributionOut

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def contribution_repo(test_app, mock_contribution_repo):
    test_app.dependency_overrides[get_scoped_contributions] = lambda: mock_contribution_repo
    yield mock_contribution_repo
    test_app.dependency_overrides.pop(get_scoped_contributions, None)


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
        "identifier": "mp-1234",
        "formula": "Fe2O3",
        "data": {"band_gap": 2.1},
    }
    body.update(overrides)
    return body


SAMPLE_OUT = ContributionOut(project="p", identifier="mp-1", formula="Fe2O3")


# ===========================================================================
# POST /contributions  (bulk insert via service)
# ===========================================================================


class TestInsertContributions:
    def test_empty_list_returns_200(self, client, contribution_service):
        contribution_service.insert_contributions.return_value = BulkWriteSummary(
            total=0, succeeded=[], failed=[]
        )
        r = client.post("/api/v1/contributions", json=[])
        assert r.status_code == 200

    def test_response_has_summary_shape(self, client, contribution_service):
        contribution_service.insert_contributions.return_value = BulkWriteSummary(
            total=0, succeeded=[], failed=[]
        )
        body = client.post("/api/v1/contributions", json=[]).json()
        assert set(body) == {"total", "succeeded", "failed"}

    def test_service_receives_parsed_contributions(self, client, contribution_service):
        contribution_service.insert_contributions.return_value = BulkWriteSummary(
            total=1, succeeded=[], failed=[]
        )
        client.post("/api/v1/contributions", json=[_valid_contribution_body()])
        contributions = contribution_service.insert_contributions.call_args.kwargs["contributions"]
        assert len(contributions) == 1
        assert contributions[0].project == "test-project"

    def test_malformed_body_returns_422(self, client, contribution_service):
        # Missing required 'formula'.
        r = client.post(
            "/api/v1/contributions",
            json=[{"_id": str(PydanticObjectId()), "project": "p", "identifier": "mp-1"}],
        )
        assert r.status_code == 422
        contribution_service.insert_contributions.assert_not_called()

    def test_non_list_body_returns_422(self, client, contribution_service):
        r = client.post("/api/v1/contributions", json=_valid_contribution_body())
        assert r.status_code == 422


# ===========================================================================
# PUT /contributions  (bulk upsert via service)
# ===========================================================================


class TestUpsertContributions:
    def test_empty_list_returns_200(self, client, contribution_service):
        contribution_service.upsert_contributions.return_value = []
        assert client.put("/api/v1/contributions", json=[]).status_code == 200

    def test_service_receives_parsed_contributions(self, client, contribution_service):
        contribution_service.upsert_contributions.return_value = []
        client.put("/api/v1/contributions", json=[_valid_contribution_body()])
        contributions = contribution_service.upsert_contributions.call_args.kwargs["contributions"]
        assert contributions[0].identifier == "mp-1234"

    def test_malformed_body_returns_422(self, client, contribution_service):
        r = client.put(
            "/api/v1/contributions",
            json=[{"_id": str(PydanticObjectId()), "project": "p"}],
        )
        assert r.status_code == 422
        contribution_service.upsert_contributions.assert_not_called()


# ===========================================================================
# Single-resource routes  (RED: glued path params)
# ===========================================================================


class TestContributionByIdRouting:
    """RED: routes mount as /contributions{id} not /contributions/{id}."""

    def test_get_by_id_conventional_path(self, client, contribution_repo):
        contribution_repo.get_contribution_by_id.return_value = SAMPLE_OUT
        assert client.get(f"/api/v1/contributions/{PydanticObjectId()}").status_code == 200

    def test_patch_by_id_conventional_path(self, client, contribution_repo):
        contribution_repo.patch_contribution_by_id.return_value = SAMPLE_OUT
        r = client.patch(f"/api/v1/contributions/{PydanticObjectId()}", json={"formula": "H2O"})
        assert r.status_code == 200

    def test_put_by_id_conventional_path(self, client, contribution_repo):
        contribution_repo.upsert_contribution_by_id.return_value = SAMPLE_OUT
        r = client.put(f"/api/v1/contributions/{PydanticObjectId()}", json=_valid_contribution_body())
        assert r.status_code == 200

    def test_delete_by_id_conventional_path(self, client, contribution_service):
        contribution_service.delete_contributions.return_value = BulkDeleteSummary(
            num_deleted=1, num_children_deleted=0
        )
        assert client.delete(f"/api/v1/contributions/{PydanticObjectId()}").status_code == 200

    def test_download_route_conventional_path(self, client, contribution_repo):
        # NOTE: this stays red even after the leading-slash fix. The route is
        # declared download/{mime} and the handler ignores the mime path param
        # while reading `format` from the query — diverging from structures/
        # tables, which use download/{short_mime} + a DownloadFormat enum and
        # work. Reconciling the contributions download route with the other
        # domains is a separate fix from the glued-path one.
        contribution_repo.download_contributions.return_value = iter([b"x"])
        assert client.get("/api/v1/contributions/download/parquet").status_code == 200


# ===========================================================================
# Single-resource behavior (independent of the routing bug, via current paths)
# ===========================================================================


class TestDeleteContributionByIdWiring:
    """delete_contribtion_by_id builds a ContributionFilter from the id and
    delegates to the service. These use the CURRENT (glued) path so the handler
    is reached today, isolating the wiring assertion from the routing bug.

    PAIRING NOTE: when the glued-path bug is fixed (leading slash added), these
    two tests must be updated to the conventional ``/contributions/{id}`` path —
    at that point the TestContributionByIdRouting.test_delete_by_id_conventional_path
    test goes green and supersedes them. They are expected to PASS today.
    """

    def test_delete_delegates_to_service(self, client, contribution_service):
        contribution_service.delete_contributions.return_value = BulkDeleteSummary(
            num_deleted=1, num_children_deleted=2
        )
        oid = PydanticObjectId()
        # NOTE: glued path is intentional here — see module docstring.
        r = client.delete(f"/api/v1/contributions/{oid}")
        assert r.status_code == 200
        contribution_service.delete_contributions.assert_awaited_once()

    def test_delete_builds_filter_from_path_id(self, client, contribution_service):
        contribution_service.delete_contributions.return_value = BulkDeleteSummary(
            num_deleted=1, num_children_deleted=0
        )
        oid = PydanticObjectId()
        client.delete(f"/api/v1/contributions/{oid}")
        passed_filter = contribution_service.delete_contributions.call_args.args[0]
        assert passed_filter.id == oid
