import pytest
from beanie import PydanticObjectId

from mpcontribs_api.authz import User
from mpcontribs_api.domains.project_groups.models import ProjectGroup, ProjectGroupIn
from mpcontribs_api.domains.project_groups.repository import ProjectGroupRepository
from mpcontribs_api.domains.project_groups.service import ProjectGroupService
from mpcontribs_api.domains.projects.models import ProjectIn, Stats
from mpcontribs_api.domains.projects.repository import MongoDbProjectRepository
from mpcontribs_api.exceptions import ConflictError, NotFoundError

pytestmark = [pytest.mark.db, pytest.mark.asyncio(loop_scope="session")]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ADMIN = User(username="google:admin@example.com", groups=frozenset({"admin"}))
ALICE = User(username="google:alice@example.com", groups=frozenset({"mp-team"}))
ANON = User()

ALICE_EMAIL = "google:alice@example.com"
BOB_EMAIL = "google:bob@example.com"
STATS = Stats(columns=0, contributions=0, tables=0, structures=0, attachments=0, size=0.0)


def _service(user: User = ADMIN) -> ProjectGroupService:
    return ProjectGroupService(groups=ProjectGroupRepository(user), projects=MongoDbProjectRepository(user))


async def _insert_project(pid: str, owner: str = ALICE_EMAIL, **overrides):
    payload = {
        "_id": pid,
        "title": pid[:30],
        "authors": "Author",
        "description": "desc",
        "owner": owner,
        "unique_identifiers": True,
        "stats": STATS,
    }
    payload.update(overrides)
    return await MongoDbProjectRepository(ADMIN).insert_project(ProjectIn(**payload))


async def _insert_group(name: str, owner: str = ALICE_EMAIL) -> ProjectGroup:
    return await ProjectGroupRepository(ADMIN).insert_project_group(
        ProjectGroupIn(name=name, owner=owner, projects=[], description="d")
    )


async def _members(group_id: PydanticObjectId) -> list[str]:
    doc = await ProjectGroup.find_one(ProjectGroup.id == group_id)
    assert doc is not None
    return sorted(link.ref.id for link in (doc.projects or []))


# ---------------------------------------------------------------------------
# add
# ---------------------------------------------------------------------------


class TestAdd:
    async def test_add_by_id_links_projects(self, db):
        group = await _insert_group("add-id")
        await _insert_project("mp-1")
        await _insert_project("mp-2")
        summary = await _service().add_projects_by_id(str(group.id), ["mp-1", "mp-2"])
        assert summary.succeeded == ["mp-1", "mp-2"]
        assert summary.failed == []
        assert await _members(group.id) == ["mp-1", "mp-2"]

    async def test_add_by_identifiers_links_projects(self, db):
        group = await _insert_group("add-ident")
        await _insert_project("mp-x")
        summary = await _service().add_projects_by_identifiers("add-ident", ALICE_EMAIL, ["mp-x"])
        assert summary.succeeded == ["mp-x"]
        assert await _members(group.id) == ["mp-x"]

    async def test_add_is_idempotent(self, db):
        group = await _insert_group("add-idem")
        await _insert_project("mp-1")
        await _service().add_projects_by_id(str(group.id), ["mp-1"])
        await _service().add_projects_by_id(str(group.id), ["mp-1"])
        assert await _members(group.id) == ["mp-1"]

    async def test_missing_project_fails_and_leaves_group_unchanged(self, db):
        group = await _insert_group("add-missing")
        summary = await _service().add_projects_by_id(str(group.id), ["ghost"])
        assert summary.succeeded == []
        assert summary.failed[0].error_code == "not_found"
        assert await _members(group.id) == []

    async def test_out_of_scope_project_fails(self, db):
        # Bob's private project is invisible to Alice, so she cannot link it.
        group = await _insert_group("add-scope")
        await _insert_project("mp-bob", owner=BOB_EMAIL)
        summary = await _service(ALICE).add_projects_by_id(str(group.id), ["mp-bob"])
        assert summary.succeeded == []
        assert summary.failed[0].error_code == "not_found"
        assert await _members(group.id) == []

    async def test_group_not_visible_raises_not_found(self, db):
        group = await _insert_group("add-priv")  # owned by Alice, invisible to anon
        with pytest.raises(NotFoundError):
            await _service(ANON).add_projects_by_id(str(group.id), [])

    async def test_ambiguous_identifiers_raise_conflict(self, db):
        # Drop the unique index so we can plant a duplicate and exercise the uniqueness guard.
        try:
            await db["project_groups"].drop_index("name_owner")
        except Exception:
            pass
        await db["project_groups"].insert_many(
            [
                {"_id": PydanticObjectId(), "name": "dup", "owner": ALICE_EMAIL, "projects": [], "description": "d"},
                {"_id": PydanticObjectId(), "name": "dup", "owner": ALICE_EMAIL, "projects": [], "description": "d"},
            ]
        )
        try:
            with pytest.raises(ConflictError):
                await _service().add_projects_by_identifiers("dup", ALICE_EMAIL, [])
        finally:
            # Restore the unique index we dropped so order-dependent tests that rely on it still see
            # it. Planted duplicates must go first, or the unique index rebuild would fail.
            await db["project_groups"].delete_many({"name": "dup"})
            await db["project_groups"].create_index(
                [("name", 1), ("owner", 1)], name="name_owner", unique=True
            )


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


class TestDelete:
    async def test_delete_by_id_unlinks_project(self, db):
        group = await _insert_group("rm-id")
        await _insert_project("mp-1")
        await _insert_project("mp-2")
        await _service().add_projects_by_id(str(group.id), ["mp-1", "mp-2"])
        summary = await _service().delete_projects_by_id(str(group.id), ["mp-1"])
        assert summary.succeeded == ["mp-1"]
        assert await _members(group.id) == ["mp-2"]

    async def test_delete_by_identifiers_unlinks_project(self, db):
        group = await _insert_group("rm-ident")
        await _insert_project("mp-1")
        await _service().add_projects_by_id(str(group.id), ["mp-1"])
        summary = await _service().delete_projects_by_identifiers("rm-ident", ALICE_EMAIL, ["mp-1"])
        assert summary.succeeded == ["mp-1"]
        assert await _members(group.id) == []

    async def test_delete_non_member_reported_as_failure(self, db):
        group = await _insert_group("rm-nonmember")
        await _insert_project("mp-1")
        await _service().add_projects_by_id(str(group.id), ["mp-1"])
        summary = await _service().delete_projects_by_id(str(group.id), ["ghost"])
        assert summary.succeeded == []
        assert summary.failed[0].error_code == "not_found"
        assert await _members(group.id) == ["mp-1"]
