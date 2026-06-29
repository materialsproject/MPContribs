import pytest

from mpcontribs_api.authz import User
from mpcontribs_api.domains.projects.models import Project, ProjectIn, ProjectOut, ProjectPatch, Stats
from mpcontribs_api.domains.projects.repository import MongoDbProjectRepository
from mpcontribs_api.exceptions import ConflictError, NotFoundError
from mpcontribs_api.pagination import CursorParams

# All tests in this module share the session event loop so they can reuse the
# session-scoped AsyncMongoClient initialised in conftest.  Beanie's internal
# collection references are loop-bound, so mixing loops causes errors.
pytestmark = [pytest.mark.db, pytest.mark.asyncio(loop_scope="session")]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

STATS = Stats(columns=0, contributions=0, tables=0, structures=0, attachments=0, size=0.0)

ADMIN = User(username="google:admin@example.com", groups=frozenset({"admin"}))
ALICE = User(username="google:alice@example.com", groups=frozenset({"mp-team"}))
ANON = User()


def _repo(user: User) -> MongoDbProjectRepository:
    return MongoDbProjectRepository(user)


def _project_in(id: str, **overrides) -> ProjectIn:
    defaults = {
        "_id": id,
        "title": id[:30],
        "authors": "Test Author",
        "description": "Test description",
        "owner": "google:alice@example.com",
        "unique_identifiers": True,
        "stats": STATS,
    }
    defaults.update(overrides)
    return ProjectIn(**defaults)


async def _insert(id: str, **overrides) -> Project:
    project_in = _project_in(id, **overrides)
    return await _repo(ADMIN).insert_project(project_in)


# ---------------------------------------------------------------------------
# insert_project
# ---------------------------------------------------------------------------


class TestInsertProject:
    async def test_inserted_project_is_retrievable(self, db):
        await _insert("ins-basic")
        found = await Project.find_one(Project.id == "ins-basic")
        assert found is not None
        assert found.id == "ins-basic"

    async def test_duplicate_id_raises_conflict(self, db):
        await _insert("ins-dup")
        with pytest.raises(ConflictError):
            await _insert("ins-dup")

    async def test_default_not_public(self, db):
        await _insert("ins-priv")
        found = await Project.find_one(Project.id == "ins-priv")
        assert found.is_public is False

    async def test_explicit_public(self, db):
        await _insert("ins-pub", is_public=True, is_approved=True)
        found = await Project.find_one(Project.id == "ins-pub")
        assert found.is_public is True


# ---------------------------------------------------------------------------
# Authorization scoping  (_build_scope)
# ---------------------------------------------------------------------------


class TestAuthorizationScope:
    async def test_admin_sees_all(self, db):
        await _insert("scope-priv", is_public=False)
        await _insert("scope-pub", is_public=True, is_approved=True)
        page = await _repo(ADMIN).get_projects(filter=_noop_filter(), pagination=CursorParams(), fields=None)
        ids = {p.id for p in page.items}
        assert "scope-priv" in ids
        assert "scope-pub" in ids

    async def test_anonymous_only_sees_public_approved(self, db):
        await _insert("anon-priv", is_public=False)
        await _insert("anon-pub", is_public=True, is_approved=True)
        await _insert("anon-pub-unapproved", is_public=True, is_approved=False)
        page = await _repo(ANON).get_projects(filter=_noop_filter(), pagination=CursorParams(), fields=None)
        ids = {p.id for p in page.items}
        assert "anon-pub" in ids
        assert "anon-priv" not in ids
        assert "anon-pub-unapproved" not in ids

    async def test_authenticated_sees_own_and_public(self, db):
        await _insert("auth-alice-priv", owner="google:alice@example.com", is_public=False)
        await _insert("auth-bob-priv", owner="google:bob@example.com", is_public=False)
        await _insert("auth-pub", is_public=True, is_approved=True)
        page = await _repo(ALICE).get_projects(filter=_noop_filter(), pagination=CursorParams(), fields=None)
        ids = {p.id for p in page.items}
        assert "auth-alice-priv" in ids
        assert "auth-pub" in ids
        assert "auth-bob-priv" not in ids


def _noop_filter():
    from mpcontribs_api.domains.projects.models import ProjectFilter

    return ProjectFilter()


# ---------------------------------------------------------------------------
# get_project_by_id
# ---------------------------------------------------------------------------


class TestGetProjectById:
    async def test_returns_project_for_valid_id(self, db):
        await _insert("get-by-id")
        result = await _repo(ADMIN).get_project_by_id(id="get-by-id", fields=None)
        assert result is not None
        assert result.id == "get-by-id"

    async def test_returns_none_for_missing_id(self, db):
        result = await _repo(ADMIN).get_project_by_id(id="does-not-exist", fields=None)
        assert result is None

    async def test_admin_can_get_private_project(self, db):
        await _insert("get-priv", is_public=False)
        result = await _repo(ADMIN).get_project_by_id(id="get-priv", fields=None)
        assert result is not None

    async def test_anon_cannot_get_private_project(self, db):
        await _insert("get-priv-anon", is_public=False)
        result = await _repo(ANON).get_project_by_id(id="get-priv-anon", fields=None)
        assert result is None


# ---------------------------------------------------------------------------
# get_projects — id filtering
#
# Regression: Beanie stores the primary key under Mongo's ``_id`` (``id`` is an
# alias), but fastapi-filter keys queries on the raw field name. Without the
# ``id`` -> ``_id`` remap in BaseFilter these filters matched nothing even
# though get_project_by_id (which queries ``_id`` directly) found the document.
# ---------------------------------------------------------------------------


class TestGetProjectsIdFilter:
    async def test_filter_by_id_matches(self, db):
        from mpcontribs_api.domains.projects.models import ProjectFilter

        await _insert("filter-id-hit")
        page = await _repo(ADMIN).get_projects(
            filter=ProjectFilter(id="filter-id-hit"), pagination=CursorParams(), fields=None
        )
        assert {p.id for p in page.items} == {"filter-id-hit"}

    async def test_filter_by_id_in_matches(self, db):
        from mpcontribs_api.domains.projects.models import ProjectFilter

        await _insert("filter-id-in-a")
        await _insert("filter-id-in-b")
        await _insert("filter-id-in-c")
        page = await _repo(ADMIN).get_projects(
            filter=ProjectFilter(id__in=["filter-id-in-a", "filter-id-in-b"]),
            pagination=CursorParams(),
            fields=None,
        )
        assert {p.id for p in page.items} == {"filter-id-in-a", "filter-id-in-b"}

    async def test_filter_by_id_neq_excludes(self, db):
        from mpcontribs_api.domains.projects.models import ProjectFilter

        await _insert("filter-id-neq-keep")
        await _insert("filter-id-neq-drop")
        page = await _repo(ADMIN).get_projects(
            filter=ProjectFilter(id__neq="filter-id-neq-drop"), pagination=CursorParams(), fields=None
        )
        ids = {p.id for p in page.items}
        assert "filter-id-neq-keep" in ids
        assert "filter-id-neq-drop" not in ids


# ---------------------------------------------------------------------------
# Field projection
# ---------------------------------------------------------------------------


class TestFieldProjection:
    async def test_projection_returns_only_requested_fields(self, db):
        await _insert("proj-fields", is_public=True, is_approved=True)
        fields = ProjectOut.parse_fields(["title"])
        page = await _repo(ADMIN).get_projects(filter=_noop_filter(), pagination=CursorParams(), fields=fields)
        assert len(page.items) == 1
        item = page.items[0]
        assert item.title == "proj-fields"
        # authors was not requested — absent from the projected model entirely
        assert not hasattr(item, "authors")

    async def test_no_projection_returns_all_fields(self, db):
        await _insert("proj-all", is_public=True, is_approved=True)
        page = await _repo(ADMIN).get_projects(filter=_noop_filter(), pagination=CursorParams(), fields=None)
        item = page.items[0]
        assert item.title is not None
        assert item.authors is not None


# ---------------------------------------------------------------------------
# Cursor-based pagination
# ---------------------------------------------------------------------------


class TestPagination:
    async def test_limit_is_respected(self, db):
        for i in range(5):
            await _insert(f"pag-limit-{i:02d}", is_public=True, is_approved=True)
        page = await _repo(ADMIN).get_projects(filter=_noop_filter(), pagination=CursorParams(limit=3), fields=None)
        assert len(page.items) == 3

    async def test_next_cursor_set_when_more_items(self, db):
        for i in range(4):
            await _insert(f"pag-cursor-{i:02d}", is_public=True, is_approved=True)
        page = await _repo(ADMIN).get_projects(filter=_noop_filter(), pagination=CursorParams(limit=2), fields=None)
        assert page.next_cursor is not None

    async def test_next_cursor_none_on_last_page(self, db):
        for i in range(3):
            await _insert(f"pag-last-{i:02d}", is_public=True, is_approved=True)
        page = await _repo(ADMIN).get_projects(filter=_noop_filter(), pagination=CursorParams(limit=10), fields=None)
        assert page.next_cursor is None

    async def test_cursor_fetches_next_page(self, db):
        for i in range(4):
            await _insert(f"pag-next-{i:02d}", is_public=True, is_approved=True)
        page1 = await _repo(ADMIN).get_projects(filter=_noop_filter(), pagination=CursorParams(limit=2), fields=None)
        assert page1.next_cursor is not None
        page2 = await _repo(ADMIN).get_projects(
            filter=_noop_filter(), pagination=CursorParams(limit=2, cursor=page1.next_cursor), fields=None
        )
        ids1 = {p.id for p in page1.items}
        ids2 = {p.id for p in page2.items}
        assert ids1.isdisjoint(ids2), "pages must not overlap"

    async def test_all_items_covered_across_pages(self, db):
        for i in range(5):
            await _insert(f"pag-all-{i:02d}", is_public=True, is_approved=True)
        all_ids: set[str] = set()
        cursor = None
        while True:
            page = await _repo(ADMIN).get_projects(
                filter=_noop_filter(), pagination=CursorParams(limit=2, cursor=cursor), fields=None
            )
            all_ids.update(p.id for p in page.items)
            cursor = page.next_cursor
            if cursor is None:
                break
        assert all(f"pag-all-{i:02d}" in all_ids for i in range(5))


# ---------------------------------------------------------------------------
# patch_project_by_id
# ---------------------------------------------------------------------------


class TestPatchProject:
    async def test_updates_single_field(self, db):
        await _insert("patch-me")
        patch = ProjectPatch(title="Updated Title")
        await _repo(ADMIN).patch_project_by_id(id="patch-me", update=patch)
        found = await Project.find_one(Project.id == "patch-me")
        assert found.title == "Updated Title"

    async def test_unset_fields_not_overwritten(self, db):
        await _insert("patch-preserve")
        original = await Project.find_one(Project.id == "patch-preserve")
        patch = ProjectPatch(title="New Title")
        await _repo(ADMIN).patch_project_by_id(id="patch-preserve", update=patch)
        found = await Project.find_one(Project.id == "patch-preserve")
        assert found.authors == original.authors

    async def test_not_found_raises(self, db):
        patch = ProjectPatch(title="Won't work")
        with pytest.raises(NotFoundError):
            await _repo(ADMIN).patch_project_by_id(id="no-such-id", update=patch)

    async def test_empty_patch_returns_existing(self, db):
        await _insert("patch-empty")
        result = await _repo(ADMIN).patch_project_by_id(id="patch-empty", update=ProjectPatch())
        assert result.id == "patch-empty"


# ---------------------------------------------------------------------------
# delete_project_by_id  (soft-delete via DocumentWithSoftDelete)
# ---------------------------------------------------------------------------


class TestDeleteProject:
    async def test_deleted_project_not_in_default_query(self, db):
        await _insert("del-me", is_public=True, is_approved=True)
        await _repo(ADMIN).delete_project_by_id(id="del-me")
        page = await _repo(ADMIN).get_projects(filter=_noop_filter(), pagination=CursorParams(), fields=None)
        ids = {p.id for p in page.items}
        assert "del-me" not in ids

    async def test_delete_nonexistent_throws_error(self, db):
        # delete_project_by_id does find_one().delete() — Error if not found
        with pytest.raises(NotFoundError, match="not found"):
            await _repo(ADMIN).delete_project_by_id(id="ghost-id")


# ---------------------------------------------------------------------------
# upsert_project_by_id
# ---------------------------------------------------------------------------


class TestUpsertProject:
    async def test_upsert_creates_new_project(self, db):
        data = _project_in("upsert-new")
        await _repo(ADMIN).upsert_project_by_id(id="upsert-new", data=data)
        found = await Project.find_one(Project.id == "upsert-new")
        assert found is not None

    async def test_upsert_updates_existing_project(self, db):
        await _insert("upsert-existing")
        data = _project_in("upsert-existing", title="Replaced Title")
        await _repo(ADMIN).upsert_project_by_id(id="upsert-existing", data=data)
        found = await Project.find_one(Project.id == "upsert-existing")
        assert found.title == "Replaced Title"

    async def test_upsert_uses_path_id_not_body_id(self, db):
        data = _project_in("body-id")
        await _repo(ADMIN).upsert_project_by_id(id="path-id", data=data)
        found = await Project.find_one(Project.id == "path-id")
        assert found is not None


# ---------------------------------------------------------------------------
# upsert_project_by_id — authorization (owner-or-admin)
# ---------------------------------------------------------------------------

BOB = User(username="google:bob@example.com", groups=frozenset())


class TestUpsertProjectAuthorization:
    async def test_owner_can_overwrite_own_project(self, db):
        await _insert("auth-own", owner="google:alice@example.com")
        data = _project_in("auth-own", owner="google:alice@example.com", title="Owner Edit")
        await _repo(ALICE).upsert_project_by_id(id="auth-own", data=data)
        found = await Project.find_one(Project.id == "auth-own")
        assert found.title == "Owner Edit"

    async def test_admin_can_overwrite_any_project(self, db):
        await _insert("auth-admin", owner="google:alice@example.com")
        data = _project_in("auth-admin", owner="google:alice@example.com", title="Admin Edit")
        await _repo(ADMIN).upsert_project_by_id(id="auth-admin", data=data)
        found = await Project.find_one(Project.id == "auth-admin")
        assert found.title == "Admin Edit"

    async def test_non_owner_cannot_overwrite(self, db):
        await _insert("auth-other", owner="google:alice@example.com", title="Original")
        data = _project_in("auth-other", owner="google:alice@example.com", title="Hijacked")
        from mpcontribs_api.exceptions import PermissionError as AppPermissionError

        with pytest.raises(AppPermissionError):
            await _repo(BOB).upsert_project_by_id(id="auth-other", data=data)
        found = await Project.find_one(Project.id == "auth-other")
        assert found.title == "Original"

    async def test_new_project_sets_owner_to_caller(self, db):
        # Body owner is someone else; the caller's identity must win.
        data = _project_in("auth-newowner", owner="google:alice@example.com")
        await _repo(BOB).upsert_project_by_id(id="auth-newowner", data=data)
        found = await Project.find_one(Project.id == "auth-newowner")
        assert found.owner == "google:bob@example.com"

    async def test_update_preserves_original_owner(self, db):
        await _insert("auth-preserve", owner="google:alice@example.com")
        # Alice tries to reassign ownership via the body; owner must stay hers.
        data = _project_in("auth-preserve", owner="google:bob@example.com", title="Edit")
        await _repo(ALICE).upsert_project_by_id(id="auth-preserve", data=data)
        found = await Project.find_one(Project.id == "auth-preserve")
        assert found.owner == "google:alice@example.com"
