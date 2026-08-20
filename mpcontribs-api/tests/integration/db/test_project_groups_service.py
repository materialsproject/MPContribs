import pytest
from beanie import PydanticObjectId

from mpcontribs_api.authz import User
from mpcontribs_api.domains.project_groups.models import ProjectGroup, ProjectGroupFilter, ProjectGroupIn
from mpcontribs_api.domains.project_groups.repository import ProjectGroupRepository
from mpcontribs_api.domains.project_groups.service import ProjectGroupService
from mpcontribs_api.domains.projects.models import ProjectIn
from mpcontribs_api.domains.projects.repository import MongoDbProjectRepository
from mpcontribs_api.exceptions import ConflictError, NotFoundError, PermissionError

pytestmark = [pytest.mark.db, pytest.mark.asyncio(loop_scope="session")]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ADMIN = User(username="google:admin@example.com", groups=frozenset({"admin"}))
ALICE = User(username="google:alice@example.com", groups=frozenset({"mp-team"}))
BOB = User(username="google:bob@example.com", groups=frozenset())
ANON = User()

ALICE_EMAIL = "google:alice@example.com"
BOB_EMAIL = "google:bob@example.com"


def _service(user: User = ADMIN) -> ProjectGroupService:
    return ProjectGroupService(user=user, groups=ProjectGroupRepository(user), projects=MongoDbProjectRepository(user))


def _role_user(group_id, username: str = "google:carol@example.com") -> User:
    """A non-owner authenticated user granted access to one group via its project-group role."""
    return User(username=username, groups=frozenset({f"project-group:{group_id}"}))


async def _insert_project(pid: str, owner: str = ALICE_EMAIL, **overrides):
    payload = {
        "title": pid[:30],
        "authors": "Author",
        "description": "desc",
        "owner": owner,
    }
    payload.update(overrides)
    return await MongoDbProjectRepository(ADMIN).insert_one(pid, ProjectIn(**payload))


async def _insert_group(name: str, owner: str = ALICE_EMAIL) -> ProjectGroup:
    return await ProjectGroupRepository(ADMIN).insert_one(
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
        summary = await _service().add_projects({"id": str(group.id)}, ["mp-1", "mp-2"])
        assert summary.succeeded == ["mp-1", "mp-2"]
        assert summary.failed == []
        assert await _members(group.id) == ["mp-1", "mp-2"]

    async def test_add_by_identifiers_links_projects(self, db):
        group = await _insert_group("add-ident")
        await _insert_project("mp-x")
        summary = await _service().add_projects({"name": "add-ident", "owner": ALICE_EMAIL}, ["mp-x"])
        assert summary.succeeded == ["mp-x"]
        assert await _members(group.id) == ["mp-x"]

    async def test_add_is_idempotent(self, db):
        group = await _insert_group("add-idem")
        await _insert_project("mp-1")
        await _service().add_projects({"id": str(group.id)}, ["mp-1"])
        await _service().add_projects({"id": str(group.id)}, ["mp-1"])
        assert await _members(group.id) == ["mp-1"]

    async def test_missing_project_fails_and_leaves_group_unchanged(self, db):
        group = await _insert_group("add-missing")
        summary = await _service().add_projects({"id": str(group.id)}, ["ghost"])
        assert summary.succeeded == []
        assert summary.failed[0].error_code == "not_found"
        assert await _members(group.id) == []

    async def test_out_of_scope_project_fails(self, db):
        # Bob's private project is invisible to Alice, so she cannot link it.
        group = await _insert_group("add-scope")
        await _insert_project("mp-bob", owner=BOB_EMAIL)
        summary = await _service(ALICE).add_projects({"id": str(group.id)}, ["mp-bob"])
        assert summary.succeeded == []
        assert summary.failed[0].error_code == "not_found"
        assert await _members(group.id) == []

    async def test_group_not_visible_raises_not_found(self, db):
        group = await _insert_group("add-priv")  # owned by Alice, invisible to anon
        with pytest.raises(NotFoundError):
            await _service(ANON).add_projects({"id": str(group.id)}, [])


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


class TestInsert:
    async def test_non_admin_owner_forced_to_caller(self, db):
        # Alice submits Bob as owner; the caller's identity must win so she can manage the group.
        group = await _service(ALICE).insert(
            ProjectGroupIn(name="ins-forced", owner=BOB_EMAIL, projects=[], description="d")
        )
        assert group.owner == ALICE_EMAIL

    async def test_admin_may_set_owner_on_behalf(self, db):
        group = await _service(ADMIN).insert(
            ProjectGroupIn(name="ins-onbehalf", owner=BOB_EMAIL, projects=[], description="d")
        )
        assert group.owner == BOB_EMAIL


class TestDelete:
    async def test_delete_by_id_unlinks_project(self, db):
        group = await _insert_group("rm-id")
        await _insert_project("mp-1")
        await _insert_project("mp-2")
        await _service().add_projects({"id": str(group.id)}, ["mp-1", "mp-2"])
        summary = await _service().delete_projects({"id": str(group.id)}, ["mp-1"])
        assert summary.succeeded == ["mp-1"]
        assert await _members(group.id) == ["mp-2"]

    async def test_delete_by_identifiers_unlinks_project(self, db):
        group = await _insert_group("rm-ident")
        await _insert_project("mp-1")
        await _service().add_projects({"id": str(group.id)}, ["mp-1"])
        summary = await _service().delete_projects({"name": "rm-ident", "owner": ALICE_EMAIL}, ["mp-1"])
        assert summary.succeeded == ["mp-1"]
        assert await _members(group.id) == []

    async def test_delete_non_member_reported_as_failure(self, db):
        group = await _insert_group("rm-nonmember")
        await _insert_project("mp-1")
        await _service().add_projects({"id": str(group.id)}, ["mp-1"])
        summary = await _service().delete_projects({"id": str(group.id)}, ["ghost"])
        assert summary.succeeded == []
        assert summary.failed[0].error_code == "not_found"
        assert await _members(group.id) == ["mp-1"]


# ---------------------------------------------------------------------------
# delete_one — owner-or-admin (403 vs 404)
# ---------------------------------------------------------------------------


class TestDeleteAuthorization:
    async def test_owner_can_delete_own(self, db):
        await _insert_group("del-own", owner=ALICE_EMAIL)
        result = await _service(ALICE).delete_one({"name": "del-own", "owner": ALICE_EMAIL})
        assert result.num_deleted == 1

    async def test_admin_can_delete_any(self, db):
        await _insert_group("del-admin", owner=ALICE_EMAIL)
        result = await _service(ADMIN).delete_one({"name": "del-admin", "owner": ALICE_EMAIL})
        assert result.num_deleted == 1

    async def test_visible_public_non_owner_forbidden(self, db):
        # Bob can *see* Alice's public group but does not own it → 403, and it is left intact.
        await ProjectGroupRepository(ADMIN).insert_one(
            ProjectGroupIn(name="del-pub", owner=ALICE_EMAIL, projects=[], description="d", is_public=True)
        )
        with pytest.raises(PermissionError):
            await _service(BOB).delete_one({"name": "del-pub", "owner": ALICE_EMAIL})
        assert await ProjectGroup.find_one(ProjectGroup.name == "del-pub") is not None

    async def test_role_holder_can_see_but_not_delete(self, db):
        # A project-group role makes the group visible, but deletion stays owner-or-admin (403).
        group = await _insert_group("del-role", owner=ALICE_EMAIL)
        with pytest.raises(PermissionError):
            await _service(_role_user(group.id)).delete_one({"name": "del-role", "owner": ALICE_EMAIL})
        assert await ProjectGroup.find_one(ProjectGroup.name == "del-role") is not None

    async def test_out_of_scope_is_not_found(self, db):
        await _insert_group("del-hidden", owner=ALICE_EMAIL)
        with pytest.raises(NotFoundError):
            await _service(ANON).delete_one({"name": "del-hidden", "owner": ALICE_EMAIL})
        assert await ProjectGroup.find_one(ProjectGroup.name == "del-hidden") is not None


# ---------------------------------------------------------------------------
# delete_many — non-admin restricted to own
# ---------------------------------------------------------------------------


class TestBulkDeleteAuthorization:
    async def test_non_admin_bulk_restricted_to_own(self, db):
        # A broad filter from a non-admin is pinned to their own groups: a public group owned by
        # someone else must survive even though the filter would otherwise match it.
        await ProjectGroupRepository(ADMIN).insert_one(
            ProjectGroupIn(name="own-bulk", owner=ALICE_EMAIL, projects=[], description="d", is_public=True)
        )
        await ProjectGroupRepository(ADMIN).insert_one(
            ProjectGroupIn(name="other-bulk", owner=BOB_EMAIL, projects=[], description="d", is_public=True)
        )
        result = await _service(ALICE).delete_many(filter=ProjectGroupFilter(is_public=True))
        assert result.num_deleted == 1
        assert await ProjectGroup.find_one(ProjectGroup.name == "own-bulk") is None
        assert await ProjectGroup.find_one(ProjectGroup.name == "other-bulk") is not None

    async def test_admin_bulk_deletes_all_matching(self, db):
        await _insert_group("abulk-1", owner=ALICE_EMAIL)
        await _insert_group("abulk-2", owner=ALICE_EMAIL)
        await _insert_group("abulk-bob", owner=BOB_EMAIL)
        result = await _service(ADMIN).delete_many(filter=ProjectGroupFilter(owner=ALICE_EMAIL))
        assert result.num_deleted == 2
        assert await ProjectGroup.find_one(ProjectGroup.owner == BOB_EMAIL) is not None
