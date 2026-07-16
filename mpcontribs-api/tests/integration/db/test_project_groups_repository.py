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
from mpcontribs_api.exceptions import ConflictError, NotFoundError, ValidationError

# Share the session event loop (see the projects repo test for why).
pytestmark = [pytest.mark.db, pytest.mark.asyncio(loop_scope="session")]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ADMIN = User(username="google:admin@example.com", groups=frozenset({"admin"}))
ALICE = User(username="google:alice@example.com", groups=frozenset({"mp-team"}))
ANON = User()

ALICE_EMAIL = "google:alice@example.com"


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
        with pytest.raises(ConflictError):
            await _repo(ADMIN).delete_project_group(name="dup", owner=ALICE_EMAIL)


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
