"""End-to-end enforcement and derivation of a project's ``columns`` on the contribution write paths.

A project's ``columns`` are the distinct dotted leaf paths across its contributions — **server-derived**,
recomputed from the stored contributions after every bulk write (see ``ContributionService.update_project``).
A client can never write them directly: ``columns`` is not a field on ``ProjectIn``/``ProjectPatch``, and a
full project replace preserves the derived set rather than accepting a body value (``TestDirectColumnWrites``).

The only way to add a column is to add a leaf to a contribution's ``data``. The per-consumer
``max_columns`` cap therefore bounds that derived set and is enforced on the *contribution* write paths,
before commit — on **create** (``insert_many``), **replace** (``upsert_many`` / ``upsert_one``) and
**update** (``update_one`` and, via ``_bulk_patch_per_row``, ``update_many``).

These drive the real service against the dev DB. ``max_columns`` is monkeypatched low to isolate the
column cap from the orthogonal per-project / per-contribution quotas.
"""

import pytest

from mpcontribs_api.authz import User
from mpcontribs_api.config import get_settings
from mpcontribs_api.domains.attachments.repository import MongoDbAttachmentRepository
from mpcontribs_api.domains.contributions.models import ContributionFilter, ContributionIn, ContributionPatch
from mpcontribs_api.domains.contributions.repository import MongoDbContributionRepository
from mpcontribs_api.domains.contributions.service import ContributionService
from mpcontribs_api.domains.initiatives.repository import MongoDbInitiativeRepository
from mpcontribs_api.domains.projects.models import Column, Project, ProjectIn
from mpcontribs_api.domains.projects.repository import MongoDbProjectRepository
from mpcontribs_api.domains.projects.service import ProjectService
from mpcontribs_api.domains.structures.repository import MongoDbStructureRepository
from mpcontribs_api.domains.tables.repository import MongoDbTableRepository
from mpcontribs_api.exceptions import ValidationError
from beanie import PydanticObjectId

pytestmark = [pytest.mark.db, pytest.mark.asyncio(loop_scope="session")]

ADMIN = User(username="google:admin@example.com", groups=frozenset({"admin"}))
PID = "col-proj"


def _service(client) -> ContributionService:
    """A ContributionService wired exactly like the FastAPI dependency, for ADMIN."""
    return ContributionService(
        client=client,
        user=ADMIN,
        projects=MongoDbProjectRepository(ADMIN),
        contributions=MongoDbContributionRepository(ADMIN),
        structures=MongoDbStructureRepository(ADMIN),
        attachments=MongoDbAttachmentRepository(ADMIN),
        tables=MongoDbTableRepository(ADMIN),
    )


def _project_service() -> ProjectService:
    """A ProjectService wired like the FastAPI dependency, for ADMIN — the direct project write path."""
    return ProjectService(
        user=ADMIN,
        projects=MongoDbProjectRepository(ADMIN),
        initiatives=MongoDbInitiativeRepository(ADMIN),
    )


async def _make_project() -> Project:
    project_in = ProjectIn(
        title="Column Cap Project",
        authors="Test Author",
        description="max_columns enforcement fixture",
        owner="google:admin@example.com",
    )
    return await MongoDbProjectRepository(ADMIN).upsert_one(Project.from_input_model(project_in, id=PID))


_MATERIAL_IDS: dict[str, str] = {}


def _material_id(label: str) -> str:
    """Map a readable label onto a stable, distinct, valid ``mp-<n>`` material_id.

    The same label always yields the same id (so re-using a label in ``_contrib`` targets the *same*
    contribution identity on replace/update), and distinct labels always yield distinct ids (so two
    contributions meant to be separate never collide on identity). Deriving the id from the label's
    letters alone would map ``"c1"`` and ``"c2"`` onto the same id — a silent identity collision — so
    a registry is used instead.
    """
    return _MATERIAL_IDS.setdefault(label, f"mp-{700 + len(_MATERIAL_IDS)}")


def _contrib(identifier: str, data: dict) -> ContributionIn:
    return ContributionIn(
        project=PID,
        material_id=_material_id(identifier),
        chemical_system_id="Fe-O",
        formula="Fe2O3",
        data=data,
    )


def _project_in_with_columns(**overrides) -> ProjectIn:
    """A project write body that *tries* to smuggle ``columns`` in — which the model must drop.

    ``columns`` is server-derived and absent from ``ProjectIn``, so ``model_validate`` ignores the
    extra key. Constructing the body this way lets a test assert the smuggled columns never land.
    """
    body = {
        "title": "Direct Columns",
        "authors": "Test Author",
        "description": "attempts to set columns directly",
        "owner": "google:admin@example.com",
        "columns": [{"path": "smuggled_a"}, {"path": "smuggled_b"}],
    }
    body.update(overrides)
    return ProjectIn.model_validate(body)


async def _project_columns() -> set[str]:
    project = await Project.find_one(Project.id == PID)
    assert project is not None
    return {c.path for c in project.columns}


@pytest.fixture(autouse=True)
def _cap_two(monkeypatch):
    """Default cap for these tests is 2 distinct columns; individual tests can override."""
    monkeypatch.setattr(get_settings().consumer.project, "max_columns", 2)


class TestCreate:
    async def test_insert_at_cap_is_allowed(self, db, mongo_client):
        await _make_project()
        summary = await _service(mongo_client).insert_many([_contrib("c1", {"a": 1.0, "b": 2.0})])
        assert summary.failed == []
        assert await _project_columns() == {"a", "b"}

    async def test_insert_new_column_over_cap_rejected(self, db, mongo_client):
        svc = _service(mongo_client)
        await _make_project()
        await svc.insert_many([_contrib("c1", {"a": 1.0, "b": 2.0})])
        # A third distinct leaf path would push the project past the cap.
        summary = await svc.insert_many([_contrib("c2", {"c": 3.0})])
        assert len(summary.succeeded) == 0
        assert len(summary.failed) == 1
        assert summary.failed[0].error_code == ValidationError.error_code
        # The rejected write left the project's columns untouched.
        assert await _project_columns() == {"a", "b"}

    async def test_insert_reusing_columns_at_cap_is_allowed(self, db, mongo_client):
        svc = _service(mongo_client)
        await _make_project()
        await svc.insert_many([_contrib("c1", {"a": 1.0, "b": 2.0})])
        # Sitting at the cap, a write that introduces no new column must still be accepted.
        summary = await svc.insert_many([_contrib("c2", {"a": 9.0})])
        assert summary.failed == []
        assert len(summary.succeeded) == 1

    async def test_in_batch_accumulation_rejects_only_the_overflow(self, db, mongo_client):
        await _make_project()
        # One batch: the first item fills the cap, the second introduces a new column and is rejected.
        summary = await _service(mongo_client).insert_many(
            [_contrib("c1", {"a": 1.0, "b": 2.0}), _contrib("c2", {"c": 3.0})]
        )
        assert len(summary.succeeded) == 1
        assert len(summary.failed) == 1
        assert summary.failed[0].index == 1
        # Only the accepted item's columns landed; the rejected item added nothing.
        assert await _project_columns() == {"a", "b"}

    async def test_insert_derives_one_column_per_nested_leaf(self, db, mongo_client, monkeypatch):
        # A column is a *leaf* path, so a nested object contributes one dotted column per leaf and
        # each counts toward the cap independently — not one column for the containing object.
        monkeypatch.setattr(get_settings().consumer.project, "max_columns", 5)
        await _make_project()
        summary = await _service(mongo_client).insert_many([_contrib("c1", {"a": {"b": 1.0, "c": 2.0}})])
        assert summary.failed == []
        assert await _project_columns() == {"a.b", "a.c"}

    async def test_two_contributions_union_their_columns(self, db, mongo_client, monkeypatch):
        # The project's column set is the union across all its contributions, not per-contribution.
        monkeypatch.setattr(get_settings().consumer.project, "max_columns", 5)
        svc = _service(mongo_client)
        await _make_project()
        await svc.insert_many([_contrib("c1", {"a": 1.0})])
        await svc.insert_many([_contrib("c2", {"b": 2.0})])
        assert await _project_columns() == {"a", "b"}


class TestReplace:
    async def test_upsert_one_over_cap_rejected(self, db, mongo_client):
        svc = _service(mongo_client)
        await _make_project()
        await svc.insert_many([_contrib("c1", {"a": 1.0, "b": 2.0})])
        with pytest.raises(ValidationError):
            await svc.upsert_one({"id": "col-proj-x"}, _contrib("c2", {"c": 3.0}))

    async def test_upsert_one_reusing_columns_at_cap_allowed(self, db, mongo_client):
        svc = _service(mongo_client)
        await _make_project()
        await svc.insert_many([_contrib("c1", {"a": 1.0, "b": 2.0})])
        # No new column -> allowed even at the cap. Upsert-by-id keys on a real ObjectId.
        result = await svc.upsert_one({"id": str(PydanticObjectId())}, _contrib("c2", {"a": 5.0}))
        assert result is not None

    async def test_upsert_many_over_cap_rejected(self, db, mongo_client):
        svc = _service(mongo_client)
        await _make_project()
        await svc.insert_many([_contrib("c1", {"a": 1.0, "b": 2.0})])
        summary = await svc.upsert_many([_contrib("c2", {"c": 3.0})])
        assert len(summary.succeeded) == 0
        assert len(summary.failed) == 1
        assert summary.failed[0].error_code == ValidationError.error_code

    async def test_upsert_many_new_contribution_derives_columns(self, db, mongo_client, monkeypatch):
        # Replace via bulk upsert: an inserted contribution's data leaves become the project's columns.
        monkeypatch.setattr(get_settings().consumer.project, "max_columns", 5)
        svc = _service(mongo_client)
        await _make_project()
        summary = await svc.upsert_many([_contrib("c1", {"a": 1.0, "b": 2.0})])
        assert summary.failed == []
        assert await _project_columns() == {"a", "b"}

    async def test_upsert_replacing_data_recomputes_columns(self, db, mongo_client, monkeypatch):
        # Re-upserting the same identity replaces the whole document, so a column present only in the
        # old data disappears and a column new to the payload appears — the project follows the data.
        monkeypatch.setattr(get_settings().consumer.project, "max_columns", 5)
        svc = _service(mongo_client)
        await _make_project()
        await svc.upsert_many([_contrib("c1", {"a": 1.0, "b": 2.0})])
        assert await _project_columns() == {"a", "b"}
        await svc.upsert_many([_contrib("c1", {"a": 1.0, "c": 3.0})])
        assert await _project_columns() == {"a", "c"}


class TestUpdate:
    async def test_update_one_adding_column_over_cap_rejected(self, db, mongo_client, monkeypatch):
        monkeypatch.setattr(get_settings().consumer.project, "max_columns", 1)
        svc = _service(mongo_client)
        await _make_project()
        summary = await svc.insert_many([_contrib("c1", {"a": 1.0})])
        cid = str(summary.succeeded[0].id)
        # Merging in a new leaf path takes the project from {a} to {a, b}, past the cap of 1.
        with pytest.raises(ValidationError):
            await svc.update_one({"id": cid}, ContributionPatch(data={"b": 2.0}))

    async def test_update_one_metadata_only_patch_is_unaffected(self, db, mongo_client, monkeypatch):
        monkeypatch.setattr(get_settings().consumer.project, "max_columns", 1)
        svc = _service(mongo_client)
        await _make_project()
        summary = await svc.insert_many([_contrib("c1", {"a": 1.0})])
        cid = str(summary.succeeded[0].id)
        # A patch that does not touch ``data`` never runs the column guard.
        updated = await svc.update_one({"id": cid}, ContributionPatch(is_public=False))
        assert updated is not None

    async def test_update_many_bulk_patch_over_cap_rejected(self, db, mongo_client, monkeypatch):
        monkeypatch.setattr(get_settings().consumer.project, "max_columns", 1)
        svc = _service(mongo_client)
        await _make_project()
        await svc.insert_many([_contrib("c1", {"a": 1.0}), _contrib("c2", {"a": 2.0})])
        # Bulk PATCH routes through _bulk_patch_per_row -> update_one, so each row hits the guard.
        summary = await svc.update_many(ContributionFilter(project=PID), ContributionPatch(data={"b": 9.0}))
        assert summary.modified == 0
        assert len(summary.failed) == 2
        assert all(f.error_code == ValidationError.error_code for f in summary.failed)
        # A rejected bulk patch adds no columns — the project stays at its pre-patch set.
        assert await _project_columns() == {"a"}

    async def test_update_many_merge_adds_column_within_cap(self, db, mongo_client, monkeypatch):
        # Update via bulk patch: merging a new leaf into each row's data adds that column to the
        # project (the write path recomputes ``columns`` for the touched project).
        monkeypatch.setattr(get_settings().consumer.project, "max_columns", 5)
        svc = _service(mongo_client)
        await _make_project()
        await svc.insert_many([_contrib("c1", {"a": 1.0})])
        summary = await svc.update_many(ContributionFilter(project=PID), ContributionPatch(data={"b": 2.0}))
        assert summary.modified == 1
        assert summary.failed == []
        assert await _project_columns() == {"a", "b"}


class TestDirectColumnWrites:
    """``columns`` cannot be set by a client directly — only derived from contributions.

    ``ProjectIn``/``ProjectPatch`` have no ``columns`` field, so a body that tries to supply one is
    dropped, and a full replace preserves the server-derived set rather than the body's. These pin
    that the *only* path to a column is through contribution ``data`` (the cap in ``ProjectIn`` /
    ``max_columns`` is enforced on the contribution write paths, not here).
    """

    async def test_columns_is_not_a_project_input_field(self):
        # The model layer is the first line of defense: ``columns`` never binds off the request body.
        assert "columns" not in ProjectIn.model_fields

    async def test_create_ignores_columns_in_body(self, db):
        # A create whose body smuggles ``columns`` lands a project with the derived (empty) set.
        await _project_service().upsert_one({"id": PID}, _project_in_with_columns())
        assert await _project_columns() == set()

    async def test_full_replace_cannot_overwrite_derived_columns(self, db, mongo_client, monkeypatch):
        # Columns derived from contributions must survive a full project replace (PUT) whose body
        # tries to set a different ``columns`` — the replace preserves the server-owned set.
        monkeypatch.setattr(get_settings().consumer.project, "max_columns", 5)
        await _make_project()
        await _service(mongo_client).insert_many([_contrib("c1", {"a": 1.0, "b": 2.0})])
        assert await _project_columns() == {"a", "b"}
        await _project_service().upsert_one({"id": PID}, _project_in_with_columns())
        # Neither the smuggled columns nor a wipe took effect: the derived set is intact.
        assert await _project_columns() == {"a", "b"}

    async def test_recompute_replaces_any_stored_columns(self, db, mongo_client, monkeypatch):
        # Even if a project somehow holds hand-written columns, the next contribution write recomputes
        # them wholesale from the contributions — the derived set is authoritative, not additive.
        monkeypatch.setattr(get_settings().consumer.project, "max_columns", 5)
        await _make_project()
        stored = await Project.find_one(Project.id == PID)
        assert stored is not None
        stored.columns = [Column(path="stale_x"), Column(path="stale_y")]
        await stored.save()
        await _service(mongo_client).insert_many([_contrib("c1", {"a": 1.0})])
        # The stale columns are gone; only what the contribution data yields remains.
        assert await _project_columns() == {"a"}
