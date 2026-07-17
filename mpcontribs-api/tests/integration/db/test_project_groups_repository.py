import pytest
from beanie import PydanticObjectId

from mpcontribs_api.authz import User
from mpcontribs_api.domains.project_groups.models import (
    ProjectGroup,
    ProjectGroupFilter,
    ProjectGroupIn,
    ProjectGroupPatch,
)
from mpcontribs_api.domains.project_groups.repository import ProjectGroupRepository
from mpcontribs_api.exceptions import ConflictError, NotFoundError, PermissionError, ValidationError
from mpcontribs_api.pagination import CursorParams

# Share the session event loop (see the projects repo test for why).
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


def _repo(user: User) -> ProjectGroupRepository:
    return ProjectGroupRepository(user)


def _group_in(name: str, owner: str = ALICE_EMAIL, **overrides) -> ProjectGroupIn:
    defaults = {
        "name": name,
        "owner": owner,
        "projects": [],
        "description": "a group",
    }
    defaults.update(overrides)
    return ProjectGroupIn(**defaults)


async def _insert(name: str, owner: str = ALICE_EMAIL, **overrides) -> ProjectGroup:
    return await _repo(ADMIN).insert_project_group(_group_in(name, owner, **overrides))


# ---------------------------------------------------------------------------
# get_one
# ---------------------------------------------------------------------------


class TestGetOne:
    async def test_returns_group_by_identifiers(self, db):
        await _insert("group-a")
        found = await _repo(ADMIN).get_project_group(name="group-a", owner=ALICE_EMAIL, fields=None)
        assert found is not None
        assert found.name == "group-a"
        assert found.owner == ALICE_EMAIL

    async def test_returns_none_when_absent(self, db):
        found = await _repo(ADMIN).get_project_group(name="missing", owner=ALICE_EMAIL, fields=None)
        assert found is None

    async def test_out_of_scope_returns_none(self, db):
        # Alice's private group is invisible to an anonymous caller.
        await _insert("group-priv")
        found = await _repo(ANON).get_project_group(name="group-priv", owner=ALICE_EMAIL, fields=None)
        assert found is None


# ---------------------------------------------------------------------------
# project-group:<oid> role scoping
# ---------------------------------------------------------------------------


def _role_user(group_id, username: str = "google:carol@example.com") -> User:
    """A non-owner authenticated user granted access to one group via its project-group role."""
    return User(username=username, groups=frozenset({f"project-group:{group_id}"}))


class TestGroupRoleScope:
    async def test_role_grants_visibility(self, db):
        group = await _insert("role-vis")  # Alice's private group
        found = await _repo(_role_user(group.id)).get_project_group(name="role-vis", owner=ALICE_EMAIL, fields=None)
        assert found is not None
        assert found.id == group.id

    async def test_without_role_not_visible(self, db):
        await _insert("role-none")
        found = await _repo(BOB).get_project_group(name="role-none", owner=ALICE_EMAIL, fields=None)
        assert found is None

    async def test_malformed_role_is_ignored(self, db):
        await _insert("role-bad")
        member = User(username="google:carol@example.com", groups=frozenset({"project-group:not-an-oid"}))
        # A malformed role id must not raise; it simply grants nothing.
        found = await _repo(member).get_project_group(name="role-bad", owner=ALICE_EMAIL, fields=None)
        assert found is None

    async def test_role_appears_in_listing(self, db):
        group = await _insert("role-list")
        page = await _repo(_role_user(group.id)).get_project_groups(
            pagination=CursorParams(), filter=ProjectGroupFilter(), fields=None
        )
        assert group.id in {g.id for g in page.items}

    async def test_role_grants_scope_but_not_delete(self, db):
        # Scope makes the group visible, but deletion remains owner-or-admin (403 for a role holder).
        group = await _insert("role-del")
        with pytest.raises(PermissionError):
            await _repo(_role_user(group.id)).delete_project_group(name="role-del", owner=ALICE_EMAIL)
        assert await ProjectGroup.find_one(ProjectGroup.name == "role-del") is not None


# ---------------------------------------------------------------------------
# delete_one  (identifier-keyed, single-resource, raises)
# ---------------------------------------------------------------------------


class TestDeleteOne:
    async def test_deletes_matching_group(self, db):
        await _insert("del-a")
        result = await _repo(ADMIN).delete_project_group(name="del-a", owner=ALICE_EMAIL)
        assert result.num_deleted == 1
        assert await ProjectGroup.find_one(ProjectGroup.name == "del-a") is None

    async def test_absent_raises_not_found(self, db):
        with pytest.raises(NotFoundError):
            await _repo(ADMIN).delete_project_group(name="nope", owner=ALICE_EMAIL)

    async def test_out_of_scope_raises_not_found(self, db):
        # Alice's group is out of scope for anon, so it "does not exist" for them.
        await _insert("del-scoped")
        with pytest.raises(NotFoundError):
            await _repo(ANON).delete_project_group(name="del-scoped", owner=ALICE_EMAIL)
        # ...and it is untouched.
        assert await ProjectGroup.find_one(ProjectGroup.name == "del-scoped") is not None

    async def test_owner_can_delete_own(self, db):
        await _insert("del-own", owner=ALICE_EMAIL)
        result = await _repo(ALICE).delete_project_group(name="del-own", owner=ALICE_EMAIL)
        assert result.num_deleted == 1

    async def test_visible_public_non_owner_forbidden(self, db):
        # Bob can *see* Alice's public group but does not own it → 403, and it is left intact.
        await _insert("del-pub", owner=ALICE_EMAIL, is_public=True)
        with pytest.raises(PermissionError):
            await _repo(BOB).delete_project_group(name="del-pub", owner=ALICE_EMAIL)
        assert await ProjectGroup.find_one(ProjectGroup.name == "del-pub") is not None

    async def test_wrong_identifier_keys_raise_validation(self, db):
        with pytest.raises(ValidationError):
            await _repo(ADMIN).delete_one({"name": "x"})  # missing 'owner'

    async def test_duplicate_identifiers_raise_conflict(self, db):
        # The name_owner unique index normally makes this impossible; drop it so we can plant a
        # duplicate and exercise the defensive uniqueness guard in _resolve_one_id. Tolerant of a
        # prior drop within the same session.
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
                await _repo(ADMIN).delete_project_group(name="dup", owner=ALICE_EMAIL)
        finally:
            # Restore the unique index we dropped so order-dependent tests that rely on it (e.g. the
            # insert-duplicate guard) still see it. Planted duplicates must go first, or the unique
            # index rebuild would fail.
            await db["project_groups"].delete_many({"name": "dup"})
            await db["project_groups"].create_index(
                [("name", 1), ("owner", 1)], name="name_owner", unique=True
            )


# ---------------------------------------------------------------------------
# patch_one
# ---------------------------------------------------------------------------


class TestPatchOne:
    async def test_updates_field(self, db):
        await _insert("patch-a", description="before")
        updated = await _repo(ADMIN).patch_project_group(
            name="patch-a", owner=ALICE_EMAIL, update=ProjectGroupPatch(description="after")
        )
        assert updated.description == "after"

    async def test_absent_raises_not_found(self, db):
        with pytest.raises(NotFoundError):
            await _repo(ADMIN).patch_project_group(
                name="ghost", owner=ALICE_EMAIL, update=ProjectGroupPatch(description="x")
            )


# ---------------------------------------------------------------------------
# delete  (arbitrary-filter bulk)
# ---------------------------------------------------------------------------


class TestDeleteByFilter:
    async def test_bulk_deletes_all_matching_owner(self, db):
        await _insert("bulk-1")
        await _insert("bulk-2")
        await _insert("other", owner="google:bob@example.com")
        result = await _repo(ADMIN).delete_project_groups(
            filter=ProjectGroupFilter(owner=ALICE_EMAIL)
        )
        assert result.num_deleted == 2
        assert await ProjectGroup.find_one(ProjectGroup.owner == "google:bob@example.com") is not None

    async def test_no_match_returns_zero(self, db):
        result = await _repo(ADMIN).delete_project_groups(
            filter=ProjectGroupFilter(owner="google:nobody@example.com")
        )
        assert result.num_deleted == 0

    async def test_non_admin_bulk_restricted_to_own(self, db):
        # A broad filter from a non-admin is pinned to their own groups: a public group owned by
        # someone else must survive even though the filter would otherwise match it.
        await _insert("own-bulk", owner=ALICE_EMAIL, is_public=True)
        await _insert("other-bulk", owner=BOB_EMAIL, is_public=True)
        result = await _repo(ALICE).delete_project_groups(filter=ProjectGroupFilter(is_public=True))
        assert result.num_deleted == 1
        assert await ProjectGroup.find_one(ProjectGroup.name == "own-bulk") is None
        assert await ProjectGroup.find_one(ProjectGroup.name == "other-bulk") is not None


# ---------------------------------------------------------------------------
# insert_project_group
#
# The input model carries no ``_id`` (the server assigns the ObjectId) and takes
# plain project ids, which from_input_model resolves into stored Links/DBRefs.
# ---------------------------------------------------------------------------


class TestInsertProjectGroup:
    async def test_assigns_object_id(self, db):
        group = await _insert("ins-oid")
        assert isinstance(group.id, PydanticObjectId)

    async def test_resolves_project_ids_to_links(self, db):
        await _insert("ins-with-projects", projects=["mp-alpha", "mp-beta"])
        doc = await ProjectGroup.find_one(ProjectGroup.name == "ins-with-projects")
        assert doc is not None
        assert doc.projects is not None
        assert {link.ref.collection for link in doc.projects} == {"projects"}
        assert sorted(link.ref.id for link in doc.projects) == ["mp-alpha", "mp-beta"]

    async def test_empty_projects_default(self, db):
        await _insert("ins-no-projects")
        doc = await ProjectGroup.find_one(ProjectGroup.name == "ins-no-projects")
        assert doc is not None
        assert doc.projects == []

    async def test_duplicate_identifiers_raise_conflict(self, db):
        # A ProjectGroup's identity is name + owner, not its server-assigned _id (a fresh ObjectId is
        # minted per insert). insert_one must reject a second group with the same name+owner cleanly.
        await _insert("ins-dup")
        with pytest.raises(ConflictError):
            await _insert("ins-dup")

    async def test_same_name_different_owner_allowed(self, db):
        # name alone is not the identity: the same name under a different owner is a distinct group.
        await _insert("ins-shared-name", owner=ALICE_EMAIL)
        other = await _insert("ins-shared-name", owner="google:bob@example.com")
        assert other.owner == "google:bob@example.com"
