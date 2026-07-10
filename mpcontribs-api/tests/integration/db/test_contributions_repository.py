import pytest
from beanie import PydanticObjectId

from mpcontribs_api.authz import User
from mpcontribs_api.domains.contributions.models import (
    Contribution,
    ContributionFilter,
    ContributionIn,
    ContributionOut,
)
from mpcontribs_api.domains.contributions.repository import MongoDbContributionRepository
from mpcontribs_api.exceptions import NotFoundError, ValidationError
from mpcontribs_api.pagination import CursorParams

pytestmark = [pytest.mark.db, pytest.mark.asyncio(loop_scope="session")]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ADMIN = User(username="google:admin@example.com", groups=frozenset({"admin"}))
ALICE = User(username="google:alice@example.com", groups=frozenset({"mp-team"}))
BOB = User(username="google:bob@example.com", groups=frozenset())
ANON = User()


def _repo(user: User = ADMIN) -> MongoDbContributionRepository:
    return MongoDbContributionRepository(user)


def _contrib_in(project: str = "test-proj", identifier: str = "mp-1", **overrides) -> ContributionIn:
    defaults: dict = {
        "_id": PydanticObjectId(),
        "project": project,
        "identifier": identifier,
        "formula": "Fe2O3",
        "data": {"band_gap": 2.1},
    }
    defaults.update(overrides)
    return ContributionIn(**defaults)


async def _insert(project="test-proj", identifier="mp-1", is_public: bool = False, **overrides) -> Contribution:
    # Build a Contribution directly so is_public can be set explicitly.
    # from_input_model() always forces is_public=False, which is correct for
    # user-submitted data but inconvenient for test setup.
    doc = Contribution(
        _id=PydanticObjectId(),
        project=project,
        identifier=identifier,
        formula=overrides.pop("formula", "Fe2O3"),
        data=overrides.pop("data", {"band_gap": 2.1}),
        is_public=is_public,
        **overrides,
    )
    await doc.insert()
    return doc


def _noop_filter() -> ContributionFilter:
    return ContributionFilter()


# ---------------------------------------------------------------------------
# insert_contribution (single)
# ---------------------------------------------------------------------------


class TestInsertContribution:
    async def test_inserted_document_is_retrievable(self, db):
        doc = await _insert(identifier="ins-basic")
        found = await Contribution.find_one(Contribution.id == doc.id)
        assert found is not None
        assert found.identifier == "ins-basic"

    async def test_is_public_defaults_to_false(self, db):
        doc = await _insert(identifier="ins-priv")
        found = await Contribution.find_one(Contribution.id == doc.id)
        assert found.is_public is False

    async def test_fields_are_persisted(self, db):
        doc = await _insert(project="proj-x", identifier="ins-fields", formula="Li2O", data={"x": 1})
        found = await Contribution.find_one(Contribution.id == doc.id)
        assert found.project == "proj-x"
        assert found.formula == "Li2O"
        assert found.data == {"x": 1}

    async def test_insert_via_repo(self, db):
        ci = _contrib_in(identifier="ins-via-repo")
        doc = Contribution.from_input_model(ci)
        result = await _repo().insert_contribution(doc)
        found = await Contribution.find_one(Contribution.id == result.id)
        assert found is not None
        assert found.identifier == "ins-via-repo"


# ---------------------------------------------------------------------------
# insert_many_contributions (bulk)
# ---------------------------------------------------------------------------


class TestInsertManyContributions:
    async def test_all_docs_persisted(self, db):
        docs = [Contribution.from_input_model(_contrib_in(identifier=f"bulk-{i}")) for i in range(5)]
        await _repo().insert_many_contributions(docs)
        for doc in docs:
            found = await Contribution.find_one(Contribution.id == doc.id)
            assert found is not None

    async def test_returns_insert_result(self, db):
        docs = [Contribution.from_input_model(_contrib_in(identifier=f"bulk-ret-{i}")) for i in range(3)]
        result = await _repo().insert_many_contributions(docs)
        assert result is not None

    async def test_empty_list_raises_type_error(self, db):
        # Motor's insert_many requires at least one document; callers are
        # responsible for guarding against empty batches.
        with pytest.raises(TypeError, match="non-empty"):
            await _repo().insert_many_contributions([])


# ---------------------------------------------------------------------------
# get_contributions (scoped list + pagination + projection)
# ---------------------------------------------------------------------------


class TestGetContributions:
    async def test_admin_sees_private_and_public(self, db):
        p = await _insert(identifier="ga-pub", is_public=True)
        pr = await _insert(identifier="ga-priv", is_public=False)
        page = await _repo(ADMIN).get_contributions(
            pagination=CursorParams(), filter=_noop_filter(), fields=None
        )
        ids = {str(c.id) for c in page.items}
        assert str(p.id) in ids
        assert str(pr.id) in ids

    async def test_anonymous_sees_only_public(self, db):
        pub = await _insert(identifier="anon-pub", is_public=True)
        priv = await _insert(identifier="anon-priv", is_public=False)
        page = await _repo(ANON).get_contributions(
            pagination=CursorParams(), filter=_noop_filter(), fields=None
        )
        ids = {str(c.id) for c in page.items}
        assert str(pub.id) in ids
        assert str(priv.id) not in ids

    async def test_authenticated_non_admin_sees_public(self, db):
        pub = await _insert(identifier="alice-pub", is_public=True)
        priv = await _insert(identifier="alice-priv", is_public=False)
        page = await _repo(ALICE).get_contributions(
            pagination=CursorParams(), filter=_noop_filter(), fields=None
        )
        ids = {str(c.id) for c in page.items}
        assert str(pub.id) in ids
        assert str(priv.id) not in ids

    async def test_response_is_page_shape(self, db):
        await _insert(identifier="pg-shape")
        page = await _repo(ADMIN).get_contributions(
            pagination=CursorParams(), filter=_noop_filter(), fields=None
        )
        assert hasattr(page, "items")
        assert hasattr(page, "next_cursor")

    async def test_limit_respected(self, db):
        for i in range(5):
            await _insert(identifier=f"lim-{i:02d}", is_public=True)
        page = await _repo(ADMIN).get_contributions(
            pagination=CursorParams(limit=3), filter=_noop_filter(), fields=None
        )
        assert len(page.items) <= 3

    async def test_cursor_paginates_forward(self, db):
        for i in range(4):
            await _insert(identifier=f"cur-{i:02d}", is_public=True)
        p1 = await _repo(ADMIN).get_contributions(
            pagination=CursorParams(limit=2), filter=_noop_filter(), fields=None
        )
        assert p1.next_cursor is not None
        p2 = await _repo(ADMIN).get_contributions(
            pagination=CursorParams(limit=2, cursor=p1.next_cursor), filter=_noop_filter(), fields=None
        )
        ids1 = {str(c.id) for c in p1.items}
        ids2 = {str(c.id) for c in p2.items}
        assert ids1.isdisjoint(ids2)

    async def test_all_items_covered_across_pages(self, db):
        for i in range(5):
            await _insert(identifier=f"all-pg-{i:02d}", is_public=True)
        identifiers: set[str] = set()
        cursor = None
        while True:
            page = await _repo(ADMIN).get_contributions(
                pagination=CursorParams(limit=2, cursor=cursor), filter=_noop_filter(), fields=None
            )
            identifiers.update(c.identifier for c in page.items if c.identifier)
            cursor = page.next_cursor
            if cursor is None:
                break
        assert all(f"all-pg-{i:02d}" in identifiers for i in range(5))

    async def test_next_cursor_none_on_last_page(self, db):
        for i in range(2):
            await _insert(identifier=f"last-pg-{i:02d}", is_public=True)
        page = await _repo(ADMIN).get_contributions(
            pagination=CursorParams(limit=100), filter=_noop_filter(), fields=None
        )
        assert page.next_cursor is None

    async def test_projection_returns_only_requested_fields(self, db):
        await _insert(identifier="proj-fields", is_public=True)
        fields = ContributionOut.parse_fields(["formula"])
        page = await _repo(ADMIN).get_contributions(
            pagination=CursorParams(), filter=_noop_filter(), fields=fields
        )
        assert len(page.items) >= 1
        item = page.items[0]
        assert item.formula is not None
        assert not hasattr(item, "data")

    async def test_filter_by_formula(self, db):
        await _insert(identifier="flt-fe", formula="Fe2O3", is_public=True)
        await _insert(identifier="flt-li", formula="Li2O", is_public=True)
        f = ContributionFilter(formula="Fe2O3")
        page = await _repo(ADMIN).get_contributions(
            pagination=CursorParams(), filter=f, fields=None
        )
        formulas = {c.formula for c in page.items}
        assert formulas == {"Fe2O3"}

    async def test_filter_by_identifier_ilike(self, db):
        await _insert(identifier="ilike-abc", is_public=True)
        await _insert(identifier="ilike-xyz", is_public=True)
        f = ContributionFilter(identifier__ilike="ilike-a")
        page = await _repo(ADMIN).get_contributions(
            pagination=CursorParams(), filter=f, fields=None
        )
        identifiers = {c.identifier for c in page.items}
        assert "ilike-abc" in identifiers
        assert "ilike-xyz" not in identifiers

    async def test_filter_by_is_public(self, db):
        await _insert(identifier="pub-only-pub", is_public=True)
        await _insert(identifier="pub-only-priv", is_public=False)
        f = ContributionFilter(is_public=True)
        page = await _repo(ADMIN).get_contributions(
            pagination=CursorParams(), filter=f, fields=None
        )
        assert all(c.is_public is True for c in page.items)

    async def test_filter_by_needs_build(self, db):
        await _insert(identifier="nb-true", needs_build=True, is_public=True)
        await _insert(identifier="nb-false", needs_build=False, is_public=True)
        f = ContributionFilter(needs_build=False)
        page = await _repo(ADMIN).get_contributions(
            pagination=CursorParams(), filter=f, fields=None
        )
        identifiers = {c.identifier for c in page.items}
        assert "nb-false" in identifiers
        assert "nb-true" not in identifiers


# ---------------------------------------------------------------------------
# get_contribution_by_id
# ---------------------------------------------------------------------------


class TestGetContributionById:
    async def test_returns_doc_for_valid_id(self, db):
        doc = await _insert(identifier="get-id")
        result = await _repo(ADMIN).get_contribution_by_id(str(doc.id), fields=None)
        assert result is not None
        assert result.identifier == "get-id"

    async def test_returns_none_for_missing_id(self, db):
        result = await _repo(ADMIN).get_contribution_by_id(str(PydanticObjectId()), fields=None)
        assert result is None

    async def test_admin_can_get_private_doc(self, db):
        doc = await _insert(identifier="get-priv", is_public=False)
        result = await _repo(ADMIN).get_contribution_by_id(str(doc.id), fields=None)
        assert result is not None

    async def test_anon_cannot_get_private_doc(self, db):
        doc = await _insert(identifier="get-anon-priv", is_public=False)
        result = await _repo(ANON).get_contribution_by_id(str(doc.id), fields=None)
        assert result is None

    async def test_anon_can_get_public_doc(self, db):
        doc = await _insert(identifier="get-anon-pub", is_public=True)
        result = await _repo(ANON).get_contribution_by_id(str(doc.id), fields=None)
        assert result is not None

    async def test_raises_validation_error_for_bad_id_format(self, db):
        with pytest.raises(ValidationError):
            await _repo(ADMIN).get_contribution_by_id("not-an-objectid", fields=None)

    async def test_projection_limits_fields(self, db):
        doc = await _insert(identifier="get-proj", is_public=True)
        fields = ContributionOut.parse_fields(["formula"])
        result = await _repo(ADMIN).get_contribution_by_id(str(doc.id), fields=fields)
        assert result is not None
        assert result.formula == "Fe2O3"
        assert not hasattr(result, "data")


# ---------------------------------------------------------------------------
# find_one_contribution (by project + identifier)
# ---------------------------------------------------------------------------


class TestFindOneContribution:
    async def test_finds_existing_doc(self, db):
        await _insert(project="find-proj", identifier="find-id")
        result = await _repo(ADMIN).find_one_contribution("find-proj", "find-id")
        assert result is not None
        assert result.project == "find-proj"
        assert result.identifier == "find-id"

    async def test_returns_none_for_missing_combination(self, db):
        await _insert(project="miss-proj", identifier="miss-id")
        result = await _repo(ADMIN).find_one_contribution("miss-proj", "wrong-id")
        assert result is None

    async def test_scope_prevents_anon_finding_private(self, db):
        await _insert(project="anon-scope", identifier="priv-doc", is_public=False)
        result = await _repo(ANON).find_one_contribution("anon-scope", "priv-doc")
        assert result is None

    async def test_scope_allows_anon_finding_public(self, db):
        await _insert(project="anon-scope-pub", identifier="pub-doc", is_public=True)
        result = await _repo(ANON).find_one_contribution("anon-scope-pub", "pub-doc")
        assert result is not None

    async def test_project_identifier_combination_is_unique_lookup(self, db):
        await _insert(project="same-proj", identifier="id-a")
        await _insert(project="same-proj", identifier="id-b")
        result = await _repo(ADMIN).find_one_contribution("same-proj", "id-a")
        assert result is not None
        assert result.identifier == "id-a"


# ---------------------------------------------------------------------------
# patch_pivot_row (scoped find-one-and-update by pivot identity)
# ---------------------------------------------------------------------------


class TestPatchPivotRow:
    async def test_updates_single_field(self, db):
        doc = await _insert(identifier="patch-formula")
        updated = await _repo(ADMIN).patch_pivot_row(
            doc.project, doc.identifier, doc.version, doc.condition_key, {"formula": "SiO2"}
        )
        assert updated is not None and updated.formula == "SiO2"
        found = await Contribution.find_one(Contribution.id == doc.id)
        assert found.formula == "SiO2"

    async def test_updates_data_field(self, db):
        doc = await _insert(identifier="patch-data")
        await _repo(ADMIN).patch_pivot_row(
            doc.project, doc.identifier, doc.version, doc.condition_key, {"data": {"energy": -5.0}}
        )
        found = await Contribution.find_one(Contribution.id == doc.id)
        assert found.data == {"energy": -5.0}

    async def test_unrelated_fields_unchanged(self, db):
        doc = await _insert(identifier="patch-preserve", formula="Fe2O3")
        await _repo(ADMIN).patch_pivot_row(
            doc.project, doc.identifier, doc.version, doc.condition_key, {"needs_build": False}
        )
        found = await Contribution.find_one(Contribution.id == doc.id)
        assert found.formula == "Fe2O3"

    async def test_no_matching_row_returns_none(self, db):
        doc = await _insert(identifier="patch-nomatch")
        result = await _repo(ADMIN).patch_pivot_row(
            doc.project, doc.identifier, doc.version, "conditions.temperature", {"formula": "X"}
        )
        assert result is None

    async def test_anon_cannot_patch_private_row(self, db):
        doc = await _insert(identifier="patch-anon-priv", is_public=False)
        # Scope hides the private row from anonymous callers, so nothing matches to update.
        result = await _repo(ANON).patch_pivot_row(
            doc.project, doc.identifier, doc.version, doc.condition_key, {"formula": "X"}
        )
        assert result is None
        still_there = await Contribution.find_one(Contribution.id == doc.id)
        assert still_there.formula == "Fe2O3"


# ---------------------------------------------------------------------------
# delete_contribution_by_id
# ---------------------------------------------------------------------------


class TestDeleteContributionById:
    async def test_deleted_doc_not_found_afterwards(self, db):
        doc = await _insert(identifier="del-me")
        await _repo(ADMIN).delete_contribution_by_id(str(doc.id))
        found = await Contribution.find_one(Contribution.id == doc.id)
        assert found is None

    async def test_delete_nonexistent_throws_error(self, db):
        with pytest.raises(NotFoundError, match="not found"):
            await _repo(ADMIN).delete_contribution_by_id(str(PydanticObjectId()))

    async def test_raises_validation_error_for_bad_id(self, db):
        with pytest.raises(ValidationError):
            await _repo(ADMIN).delete_contribution_by_id("not-an-id")

    async def test_anon_cannot_delete_private_doc(self, db):
        doc = await _insert(identifier="del-anon-priv", is_public=False)
        with pytest.raises(NotFoundError, match="not found"):
            await _repo(ANON).delete_contribution_by_id(str(doc.id))
        # Scope prevents anonymous from seeing the doc, so it is never deleted.
        still_there = await Contribution.find_one(Contribution.id == doc.id)
        assert still_there is not None


# ---------------------------------------------------------------------------
# delete_contributions (bulk with filter)
# ---------------------------------------------------------------------------


class TestDeleteContributions:
    async def test_bulk_delete_all(self, db):
        for i in range(3):
            await _insert(identifier=f"bdel-{i:02d}")
        await _repo(ADMIN).delete_contributions(_noop_filter())
        remaining = await Contribution.find().to_list()
        assert len(remaining) == 0

    async def test_bulk_delete_with_filter(self, db):
        await _insert(identifier="bdel-keep", formula="Li2O")
        await _insert(identifier="bdel-drop", formula="Fe2O3")
        f = ContributionFilter(formula="Fe2O3")
        await _repo(ADMIN).delete_contributions(f)
        remaining = await Contribution.find().to_list()
        assert len(remaining) == 1
        assert remaining[0].identifier == "bdel-keep"

    async def test_bulk_delete_empty_collection_is_silent(self, db):
        await _repo(ADMIN).delete_contributions(_noop_filter())

    async def test_scope_limits_what_anon_can_delete(self, db):
        await _insert(identifier="bdel-scope-pub", is_public=True)
        await _insert(identifier="bdel-scope-priv", is_public=False)
        await _repo(ANON).delete_contributions(_noop_filter())
        # Anonymous scope: only public visible, so only the public doc is deleted.
        remaining = await Contribution.find().to_list()
        identifiers = {d.identifier for d in remaining}
        assert "bdel-scope-priv" in identifiers


class TestUpsertContributionById:
    async def test_insert_when_id_absent_persists_document(self, db):
        new_id = PydanticObjectId()
        payload = _contrib_in(identifier="ups-new", _id=new_id)
        result = await _repo(ADMIN).upsert_contribution_by_id(str(new_id), payload)
        # Must be the resolved document, not an un-awaited query object.
        assert isinstance(result, Contribution)
        stored = await Contribution.find_one(Contribution.id == new_id)
        assert stored is not None
        assert stored.identifier == "ups-new"

    async def test_update_when_id_present_applies_change(self, db):
        existing = await _insert(identifier="ups-existing")
        payload = _contrib_in(identifier="ups-existing", formula="Li2O", _id=existing.id)
        result = await _repo(ADMIN).upsert_contribution_by_id(str(existing.id), payload)
        assert isinstance(result, Contribution)
        stored = await Contribution.find_one(Contribution.id == existing.id)
        assert stored is not None
        assert stored.formula == "Li2O"


class TestDeleteByIdsScope:
    async def test_anon_cannot_delete_out_of_scope_ids(self, db):
        pub = await _insert(identifier="dbi-pub", is_public=True)
        priv = await _insert(identifier="dbi-priv", is_public=False)
        # Anonymous scope only sees public docs; deleting both ids must spare the private one.
        result = await _repo(ANON).delete_by_ids([pub.id, priv.id])
        assert result.num_deleted == 1
        remaining = {d.identifier for d in await Contribution.find().to_list()}
        assert "dbi-priv" in remaining
        assert "dbi-pub" not in remaining

    async def test_admin_deletes_all_ids(self, db):
        a = await _insert(identifier="dbi-a", is_public=False)
        b = await _insert(identifier="dbi-b", is_public=False)
        result = await _repo(ADMIN).delete_by_ids([a.id, b.id])
        assert result.num_deleted == 2
