import pytest
from beanie import PydanticObjectId

from mpcontribs_api.authz import User
from mpcontribs_api.domains.contributions.models import (
    Contribution,
    ContributionFilter,
    ContributionOut,
)
from mpcontribs_api.domains.contributions.repository import MongoDbContributionRepository
from mpcontribs_api.exceptions import ConflictError, ValidationError
from mpcontribs_api.pagination import CursorParams

pytestmark = [pytest.mark.db, pytest.mark.asyncio(loop_scope="session")]


# ---------------------------------------------------------------------------
# Helpers
#
# Contributions are worker-written, so the repository is read-only here. Tests seed the collection
# directly via ``Contribution(...).insert()`` (there is no input/write path on this server) and then
# exercise the read methods.
# ---------------------------------------------------------------------------

ADMIN = User(username="google:admin@example.com", groups=frozenset({"admin"}))
ALICE = User(username="google:alice@example.com", groups=frozenset({"mp-team"}))
BOB = User(username="google:bob@example.com", groups=frozenset())
ANON = User()


def _repo(user: User = ADMIN) -> MongoDbContributionRepository:
    return MongoDbContributionRepository(user)


async def _insert(
    project="test-proj",
    identifier="mp-1",
    chemical_system_id="Fe-O",
    is_public: bool = False,
    **overrides,
) -> Contribution:
    """Seed a Contribution directly. ``identifier`` maps onto ``material_id`` so the default
    chemical_system_id/formula give each contribution a distinct identity tuple."""
    doc = Contribution(
        _id=PydanticObjectId(),
        project=project,
        material_id=identifier,
        chemical_system_id=chemical_system_id,
        formula=overrides.pop("formula", "Fe2O3"),
        data=overrides.pop("data", {"bandGap": 2.1}),
        is_public=is_public,
        **overrides,
    )
    await doc.insert()
    return doc


def _noop_filter() -> ContributionFilter:
    return ContributionFilter()


def _identity(
    project="test-proj",
    material_id="mp-1",
    chemical_system_id="Fe-O",
    formula="Fe2O3",
    unique_value=None,
    condition_key="",
) -> dict:
    """The full composite natural key (see ``ContributionIdentity.model_fields``) for a semantic lookup.

    Mirrors the defaults ``_insert`` seeds, so ``_identity(material_id=...)`` addresses a document
    created with the matching ``identifier=...``.
    """
    return {
        "project": project,
        "material_id": material_id,
        "chemical_system_id": chemical_system_id,
        "formula": formula,
        "unique_value": unique_value,
        "condition_key": condition_key,
    }


# ---------------------------------------------------------------------------
# read_many (scoped list / pagination / filtering)
# ---------------------------------------------------------------------------


class TestGetContributions:
    async def test_admin_sees_private_and_public(self, db):
        p = await _insert(identifier="ga-pub", is_public=True)
        pr = await _insert(identifier="ga-priv", is_public=False)
        page = await _repo(ADMIN).read_many(pagination=CursorParams(), filter=_noop_filter(), fields=None)
        ids = {str(c.id) for c in page.items}
        assert str(p.id) in ids
        assert str(pr.id) in ids

    async def test_anonymous_sees_only_public(self, db):
        pub = await _insert(identifier="anon-pub", is_public=True)
        priv = await _insert(identifier="anon-priv", is_public=False)
        page = await _repo(ANON).read_many(pagination=CursorParams(), filter=_noop_filter(), fields=None)
        ids = {str(c.id) for c in page.items}
        assert str(pub.id) in ids
        assert str(priv.id) not in ids

    async def test_authenticated_non_admin_sees_public(self, db):
        pub = await _insert(identifier="alice-pub", is_public=True)
        priv = await _insert(identifier="alice-priv", is_public=False)
        page = await _repo(ALICE).read_many(pagination=CursorParams(), filter=_noop_filter(), fields=None)
        ids = {str(c.id) for c in page.items}
        assert str(pub.id) in ids
        assert str(priv.id) not in ids

    async def test_response_is_page_shape(self, db):
        await _insert(identifier="pg-shape")
        page = await _repo(ADMIN).read_many(pagination=CursorParams(), filter=_noop_filter(), fields=None)
        assert hasattr(page, "items")
        assert hasattr(page, "next_cursor")

    async def test_limit_respected(self, db):
        for i in range(5):
            await _insert(identifier=f"lim-{i:02d}", is_public=True)
        page = await _repo(ADMIN).read_many(pagination=CursorParams(limit=3), filter=_noop_filter(), fields=None)
        assert len(page.items) <= 3

    async def test_cursor_paginates_forward(self, db):
        for i in range(4):
            await _insert(identifier=f"cur-{i:02d}", is_public=True)
        p1 = await _repo(ADMIN).read_many(pagination=CursorParams(limit=2), filter=_noop_filter(), fields=None)
        assert p1.next_cursor is not None
        p2 = await _repo(ADMIN).read_many(
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
            page = await _repo(ADMIN).read_many(
                pagination=CursorParams(limit=2, cursor=cursor), filter=_noop_filter(), fields=None
            )
            identifiers.update(c.material_id for c in page.items if c.material_id)
            cursor = page.next_cursor
            if cursor is None:
                break
        assert all(f"all-pg-{i:02d}" in identifiers for i in range(5))

    async def test_next_cursor_none_on_last_page(self, db):
        for i in range(2):
            await _insert(identifier=f"last-pg-{i:02d}", is_public=True)
        page = await _repo(ADMIN).read_many(pagination=CursorParams(limit=100), filter=_noop_filter(), fields=None)
        assert page.next_cursor is None

    async def test_projection_returns_only_requested_fields(self, db):
        await _insert(identifier="proj-fields", is_public=True)
        fields = ContributionOut.parse_fields(["formula"])
        page = await _repo(ADMIN).read_many(pagination=CursorParams(), filter=_noop_filter(), fields=fields)
        assert len(page.items) >= 1
        item = page.items[0]
        assert item.formula is not None
        assert not hasattr(item, "data")

    async def test_filter_by_formula(self, db):
        await _insert(identifier="flt-fe", formula="Fe2O3", is_public=True)
        await _insert(identifier="flt-li", formula="Li2O", is_public=True)
        f = ContributionFilter(formula="Fe2O3")
        page = await _repo(ADMIN).read_many(pagination=CursorParams(), filter=f, fields=None)
        formulas = {c.formula for c in page.items}
        assert formulas == {"Fe2O3"}

    async def test_filter_by_material_id_ilike(self, db):
        await _insert(identifier="ilike-abc", is_public=True)
        await _insert(identifier="ilike-xyz", is_public=True)
        f = ContributionFilter(material_id__ilike="ilike-a")
        page = await _repo(ADMIN).read_many(pagination=CursorParams(), filter=f, fields=None)
        identifiers = {c.material_id for c in page.items}
        assert "ilike-abc" in identifiers
        assert "ilike-xyz" not in identifiers

    async def test_filter_by_is_public(self, db):
        await _insert(identifier="pub-only-pub", is_public=True)
        await _insert(identifier="pub-only-priv", is_public=False)
        f = ContributionFilter(is_public=True)
        page = await _repo(ADMIN).read_many(pagination=CursorParams(), filter=f, fields=None)
        assert all(c.is_public is True for c in page.items)


# ---------------------------------------------------------------------------
# read_one (by id)
# ---------------------------------------------------------------------------


class TestGetContributionById:
    async def test_returns_doc_for_valid_id(self, db):
        doc = await _insert(identifier="get-id")
        result = await _repo(ADMIN).read_one({"id": doc.id}, fields=None)
        assert result is not None
        assert result.material_id == "get-id"

    async def test_returns_none_for_missing_id(self, db):
        assert await _repo(ADMIN).read_one({"id": PydanticObjectId()}, fields=None) is None

    async def test_admin_can_get_private_doc(self, db):
        doc = await _insert(identifier="get-priv", is_public=False)
        result = await _repo(ADMIN).read_one({"id": doc.id}, fields=None)
        assert result is not None

    async def test_anon_cannot_get_private_doc(self, db):
        doc = await _insert(identifier="get-anon-priv", is_public=False)
        assert await _repo(ANON).read_one({"id": doc.id}, fields=None) is None

    async def test_anon_can_get_public_doc(self, db):
        doc = await _insert(identifier="get-anon-pub", is_public=True)
        result = await _repo(ANON).read_one({"id": doc.id}, fields=None)
        assert result is not None

    async def test_projection_limits_fields(self, db):
        doc = await _insert(identifier="get-proj", is_public=True)
        fields = ContributionOut.parse_fields(["formula"])
        result = await _repo(ADMIN).read_one({"id": doc.id}, fields=fields)
        assert result is not None
        assert result.formula == "Fe2O3"
        assert not hasattr(result, "data")


# ---------------------------------------------------------------------------
# read_one (by the semantic composite identity)
# ---------------------------------------------------------------------------


class TestGetContributionBySemanticIdentifiers:
    async def test_finds_existing_doc(self, db):
        await _insert(project="find-proj", identifier="find-id")
        result = await _repo(ADMIN).read_one(_identity(project="find-proj", material_id="find-id"), fields=None)
        assert result is not None
        assert result.project == "find-proj"
        assert result.material_id == "find-id"

    async def test_returns_none_for_missing_combination(self, db):
        await _insert(project="miss-proj", identifier="miss-id")
        assert await _repo(ADMIN).read_one(_identity(project="miss-proj", material_id="wrong-id"), fields=None) is None

    async def test_scope_prevents_anon_finding_private(self, db):
        await _insert(project="anon-scope", identifier="priv-doc", is_public=False)
        assert await _repo(ANON).read_one(_identity(project="anon-scope", material_id="priv-doc"), fields=None) is None

    async def test_scope_allows_anon_finding_public(self, db):
        await _insert(project="anon-scope-pub", identifier="pub-doc", is_public=True)
        result = await _repo(ANON).read_one(_identity(project="anon-scope-pub", material_id="pub-doc"), fields=None)
        assert result is not None

    async def test_composite_identity_is_unique_lookup(self, db):
        await _insert(project="same-proj", identifier="id-a")
        await _insert(project="same-proj", identifier="id-b")
        result = await _repo(ADMIN).read_one(_identity(project="same-proj", material_id="id-a"), fields=None)
        assert result is not None
        assert result.material_id == "id-a"

    async def test_partial_identity_resolves_matching_doc(self, db):
        # A partial identity (a subset of the composite key) is accepted, as long as it satisfies the
        # hierarchy, and resolves the single matching row.
        await _insert(project="partial-proj", identifier="partial-id", chemical_system_id="Fe-O")
        result = await _repo(ADMIN).read_one({"project": "partial-proj", "chemical_system_id": "Fe-O"}, fields=None)
        assert result is not None
        assert result.material_id == "partial-id"

    async def test_partial_identity_ambiguous_raises_conflict(self, db):
        # A partial identity that matches more than one in-scope row is rejected rather than silently
        # returning the first — the caller must disambiguate (e.g. supply material_id/formula).
        await _insert(project="ambig-proj", identifier="mp-1", chemical_system_id="Fe-O")
        await _insert(project="ambig-proj", identifier="mp-2", chemical_system_id="Fe-O")
        with pytest.raises(ConflictError):
            await _repo(ADMIN).read_one({"project": "ambig-proj", "chemical_system_id": "Fe-O"}, fields=None)

    async def test_identity_without_chemical_system_is_rejected(self, db):
        # The identifier hierarchy requires chemical_system_id; a partial lacking it is invalid.
        await _insert(project="no-chemsys", identifier="mp-1")
        with pytest.raises(ValidationError):
            await _repo(ADMIN).read_one({"project": "no-chemsys", "material_id": "mp-1"}, fields=None)
