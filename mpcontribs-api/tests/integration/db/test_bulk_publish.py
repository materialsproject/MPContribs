import pytest

from mpcontribs_api.authz import User
from mpcontribs_api.domains._shared.units import QuantityLeaf
from mpcontribs_api.domains.attachments.repository import MongoDbAttachmentRepository
from mpcontribs_api.domains.contributions.models import (
    Contribution,
    ContributionFilter,
    ContributionIn,
    ContributionPatch,
)
from mpcontribs_api.domains.contributions.repository import MongoDbContributionRepository
from mpcontribs_api.domains.contributions.service import ContributionService
from mpcontribs_api.domains.projects.repository import MongoDbProjectRepository
from mpcontribs_api.domains.structures.repository import MongoDbStructureRepository
from mpcontribs_api.domains.tables.repository import MongoDbTableRepository

pytestmark = [pytest.mark.db, pytest.mark.asyncio(loop_scope="session")]

# ALICE may write only PROJ_A; PROJ_B is foreign to her. ADMIN may write anything.
ALICE = User(username="google:alice@example.com", groups=frozenset({"proj-a"}))
ADMIN = User(username="google:admin@example.com", groups=frozenset({"admin"}))
PROJ_A = "proj-a"
PROJ_B = "proj-b"


def _service(client, user: User) -> ContributionService:
    """A ContributionService wired exactly like the FastAPI dependency, for ``user``."""
    return ContributionService(
        client=client,
        user=user,
        projects=MongoDbProjectRepository(user),
        contributions=MongoDbContributionRepository(user),
        structures=MongoDbStructureRepository(user),
        attachments=MongoDbAttachmentRepository(user),
        tables=MongoDbTableRepository(user),
    )


async def _insert(project: str, identifier: str, *, is_public: bool) -> Contribution:
    """Insert one contribution directly (bypassing the write pipeline) with a chosen visibility.

    ``identifier`` is a human label only; each case here uses a distinct project, so the identity
    tuple (project + chemical_system_id + formula) is unique without a material_id.
    """
    doc = Contribution.from_input_model(
        ContributionIn(project=project, chemical_system_id="Fe-O", formula="Fe2O3", data={"x": 1.0})
    )
    doc.is_public = is_public
    await doc.insert()
    return doc


async def _is_public(cid) -> bool:
    found = await Contribution.find_one(Contribution.id == cid)
    assert found is not None
    return found.is_public


class TestBulkPublishAuthorization:
    async def test_publishes_only_writable_projects(self, db, mongo_client):
        # Alice's own project is private-but-writable; the foreign project is out of her write scope.
        a = await _insert(PROJ_A, "c1", is_public=False)
        b = await _insert(PROJ_B, "c1", is_public=False)

        summary = await _service(mongo_client, ALICE).patch_many(
            ContributionFilter(), ContributionPatch(is_public=True)
        )

        assert summary.projects == [PROJ_A]
        assert (summary.matched, summary.modified) == (1, 1)
        assert await _is_public(a.id) is True
        assert await _is_public(b.id) is False  # foreign project untouched

    async def test_public_in_other_project_not_modified(self, db, mongo_client):
        # A public contribution in a foreign project is *readable* by Alice (scope), but the bulk
        # update constrains to writable projects, so a filter matching it modifies nothing.
        b = await _insert(PROJ_B, "pub", is_public=True)

        summary = await _service(mongo_client, ALICE).patch_many(
            ContributionFilter(is_public=True), ContributionPatch(is_public=False)
        )

        assert (summary.matched, summary.modified) == (0, 0)
        assert summary.projects == []
        assert await _is_public(b.id) is True  # still public

    async def test_admin_is_unconstrained_by_project(self, db, mongo_client):
        a = await _insert(PROJ_A, "c1", is_public=False)
        b = await _insert(PROJ_B, "c1", is_public=False)

        summary = await _service(mongo_client, ADMIN).patch_many(
            ContributionFilter(), ContributionPatch(is_public=True)
        )

        assert set(summary.projects) == {PROJ_A, PROJ_B}
        assert (summary.matched, summary.modified) == (2, 2)
        assert await _is_public(a.id) is True
        assert await _is_public(b.id) is True


class TestSinglePublish:
    async def test_patch_by_id_publishes_single_contribution(self, db, mongo_client):
        a = await _insert(PROJ_A, "c1", is_public=False)

        result = await _service(mongo_client, ALICE).patch_one(
            {"id": str(a.id)}, ContributionPatch(is_public=True)
        )

        assert result.is_public is True
        assert await _is_public(a.id) is True


async def _insert_row(project: str, *, formula: str, data: dict) -> Contribution:
    """Insert one contribution with a chosen formula/data so callers control the identity tuple."""
    doc = Contribution.from_input_model(
        ContributionIn(project=project, chemical_system_id="Fe-O", formula=formula, data=data)
    )
    await doc.insert()
    return doc


async def _reload(cid) -> Contribution:
    found = await Contribution.find_one(Contribution.id == cid)
    assert found is not None
    return found


class TestBulkPatchPerRow:
    """Filter patches that touch identity inputs run per row (recompute + collision reporting)."""

    async def test_bulk_data_patch_merges_into_every_matched_row(self, db, mongo_client):
        # Two distinct identities in Alice's writable project; a data patch is merged into both so
        # each row keeps its own pre-existing ``x`` and gains the patched ``y``.
        a = await _insert_row(PROJ_A, formula="Fe2O3", data={"x": 1.0})
        b = await _insert_row(PROJ_A, formula="Fe3O4", data={"x": 2.0})

        summary = await _service(mongo_client, ALICE).patch_many(
            ContributionFilter(chemical_system_id="Fe-O"), ContributionPatch(data={"y": 9.0})
        )

        assert (summary.matched, summary.modified) == (2, 2)
        assert summary.projects == [PROJ_A]
        assert summary.failed == []
        # Additive by default: the unmentioned ``x`` survives on each row; ``y`` is added.
        assert (await _reload(a.id)).data == {"x": 1.0, "y": 9.0}
        assert (await _reload(b.id)).data == {"x": 2.0, "y": 9.0}

    async def test_bulk_data_patch_replaces_data_when_replace_data_set(self, db, mongo_client):
        # replace_data=True overwrites each row's ``data`` wholesale, dropping the unmentioned ``x``.
        a = await _insert_row(PROJ_A, formula="Fe2O3", data={"x": 1.0})
        b = await _insert_row(PROJ_A, formula="Fe3O4", data={"x": 2.0})

        summary = await _service(mongo_client, ALICE).patch_many(
            ContributionFilter(chemical_system_id="Fe-O"),
            ContributionPatch(data={"y": 9.0}),
            replace_data=True,
        )

        assert (summary.matched, summary.modified) == (2, 2)
        for cid in (a.id, b.id):
            assert (await _reload(cid)).data == {"y": 9.0}

    async def test_bare_scalar_updates_quantity_leaf_magnitude(self, db, mongo_client):
        # A stored quantity leaf is conceptually a scalar: a bare-scalar patch is the new submitted
        # magnitude. The leaf is re-derived end-to-end (unit kept, input_value updated), and the
        # persisted leaf matches the pure patch_leaf helper.
        leaf = QuantityLeaf.from_submission(2.0, "m").as_dict()
        c = await _insert_row(PROJ_A, formula="Fe2O3", data={"bandgap": leaf})

        summary = await _service(mongo_client, ALICE).patch_many(
            ContributionFilter(chemical_system_id="Fe-O"), ContributionPatch(data={"bandgap": 5.0})
        )

        assert (summary.matched, summary.modified) == (1, 1)
        reloaded = (await _reload(c.id)).data["bandgap"]
        assert reloaded == QuantityLeaf.patch_leaf(leaf, {"value": 5.0})
        assert reloaded["input_value"] == 5.0
        assert reloaded["unit"] == "m"

    async def test_unit_change_re_syncs_and_re_converts_leaf(self, db, mongo_client):
        # Updating the unit re-canonicalizes the whole leaf: input_unit tracks the new unit and the
        # canonical value/error are re-converted to SI (2 m -> input 2 km -> 2000 m).
        leaf = QuantityLeaf.from_submission(2.0, "m").as_dict()
        c = await _insert_row(PROJ_A, formula="Fe2O3", data={"bandgap": leaf})

        summary = await _service(mongo_client, ALICE).patch_many(
            ContributionFilter(chemical_system_id="Fe-O"), ContributionPatch(data={"bandgap": {"unit": "km"}})
        )

        assert (summary.matched, summary.modified) == (1, 1)
        reloaded = (await _reload(c.id)).data["bandgap"]
        assert reloaded == QuantityLeaf.patch_leaf(leaf, {"unit": "km"})
        assert reloaded["input_unit"] == "km"
        assert reloaded["input_value"] == 2.0
        assert reloaded["value"] == 2000.0

    async def test_identity_collision_reports_per_row_conflict(self, db, mongo_client):
        # Setting formula to a value another matched row already owns collides on the identity index:
        # the already-Fe2O3 row is a no-op success, the Fe3O4 row conflicts against it.
        keep = await _insert_row(PROJ_A, formula="Fe2O3", data={"x": 1.0})
        clash = await _insert_row(PROJ_A, formula="Fe3O4", data={"x": 2.0})

        summary = await _service(mongo_client, ALICE).patch_many(
            ContributionFilter(chemical_system_id="Fe-O"), ContributionPatch(formula="Fe2O3")
        )

        assert summary.matched == 2
        assert summary.modified == 1
        assert len(summary.failed) == 1
        assert summary.failed[0].error_code == "conflict"
        # The clashing row is left untouched; the pre-existing Fe2O3 row is unchanged.
        assert (await _reload(clash.id)).formula == "Fe3O4"
        assert (await _reload(keep.id)).formula == "Fe2O3"

    async def test_per_row_patch_respects_writable_constraint(self, db, mongo_client):
        # A data patch (identity-touching) must honor the same writable-project gate as the fast path:
        # Alice's row is patched, the foreign-project row (readable-but-not-writable) is not.
        mine = await _insert_row(PROJ_A, formula="Fe2O3", data={"x": 1.0})
        foreign = Contribution.from_input_model(
            ContributionIn(project=PROJ_B, chemical_system_id="Fe-O", formula="Fe2O3", data={"x": 1.0})
        )
        foreign.is_public = True
        await foreign.insert()

        summary = await _service(mongo_client, ALICE).patch_many(
            ContributionFilter(chemical_system_id="Fe-O"), ContributionPatch(data={"y": 9.0})
        )

        assert (summary.matched, summary.modified) == (1, 1)
        assert summary.projects == [PROJ_A]
        assert (await _reload(mine.id)).data == {"x": 1.0, "y": 9.0}  # merged, not replaced
        assert (await _reload(foreign.id)).data == {"x": 1.0}  # foreign project untouched
