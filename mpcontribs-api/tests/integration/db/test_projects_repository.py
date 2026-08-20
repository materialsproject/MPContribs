import pytest

from mpcontribs_api.authz import User
from mpcontribs_api.domains.projects.models import Project, ProjectIn, ProjectOut, ProjectPatch
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

ADMIN = User(username="google:admin@example.com", groups=frozenset({"admin"}))
ALICE = User(username="google:alice@example.com", groups=frozenset({"mp-team"}))
BOB = User(username="google:bob@example.com", groups=frozenset())
ANON = User()

ALICE_EMAIL = "google:alice@example.com"
BOB_EMAIL = "google:bob@example.com"


def _repo(user: User) -> MongoDbProjectRepository:
    return MongoDbProjectRepository(user)


def _project_in(id: str, **overrides) -> ProjectIn:
    """Build a user-supplied ``ProjectIn`` (content fields only — no server-managed id/stats)."""
    defaults = {
        "title": id[:30],
        "authors": "Test Author",
        "description": "Test description",
        "owner": ALICE_EMAIL,
    }
    defaults.update(overrides)
    return ProjectIn(**defaults)


async def _insert(id: str, **overrides) -> Project:
    """Seed a project via the repository's mechanical insert path (admin, no policy)."""
    return await _repo(ADMIN).insert_one(id, _project_in(id, **overrides))


def _noop_filter():
    from mpcontribs_api.domains.projects.models import ProjectFilter

    return ProjectFilter()


# ---------------------------------------------------------------------------
# insert_one  (mechanical: id-stamp + dup-reject, no policy)
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

    async def test_insert_defaults_private_and_unapproved(self, db):
        # ProjectIn carries no is_public/is_approved, so an inserted project is private and unapproved.
        await _insert("ins-priv")
        found = await Project.find_one(Project.id == "ins-priv")
        assert found.is_public is False
        assert found.is_approved is False


# ---------------------------------------------------------------------------
# Authorization scoping  (read visibility via the repo's declared Scope)
# ---------------------------------------------------------------------------


class TestAuthorizationScope:
    async def test_admin_sees_all(self, db):
        await _insert("scope-priv", is_public=False)
        await _insert("scope-pub", is_public=True, is_approved=True)
        page = await _repo(ADMIN).get_many(filter=_noop_filter(), pagination=CursorParams(), fields=None)
        ids = {p.id for p in page.items}
        assert "scope-priv" in ids
        assert "scope-pub" in ids

    async def test_anonymous_only_sees_public_approved(self, db):
        await _insert("anon-priv", is_public=False)
        await _insert("anon-pub", is_public=True, is_approved=True)
        await _insert("anon-pub-unapproved", is_public=True, is_approved=False)
        page = await _repo(ANON).get_many(filter=_noop_filter(), pagination=CursorParams(), fields=None)
        ids = {p.id for p in page.items}
        assert "anon-pub" in ids
        assert "anon-priv" not in ids
        assert "anon-pub-unapproved" not in ids

    async def test_authenticated_sees_own_and_public(self, db):
        await _insert("auth-alice-priv", owner=ALICE_EMAIL, is_public=False)
        await _insert("auth-bob-priv", owner=BOB_EMAIL, is_public=False)
        await _insert("auth-pub", is_public=True, is_approved=True)
        page = await _repo(ALICE).get_many(filter=_noop_filter(), pagination=CursorParams(), fields=None)
        ids = {p.id for p in page.items}
        assert "auth-alice-priv" in ids
        assert "auth-pub" in ids
        assert "auth-bob-priv" not in ids

    async def test_group_member_sees_granted_private_project(self, db):
        # A bare project role (the project id) grants visibility of an otherwise-private project.
        member = User(username="google:carol@example.com", groups=frozenset({"scope-granted"}))
        await _insert("scope-granted", owner=ALICE_EMAIL, is_public=False)
        page = await _repo(member).get_many(filter=_noop_filter(), pagination=CursorParams(), fields=None)
        assert "scope-granted" in {p.id for p in page.items}


# ---------------------------------------------------------------------------
# get_one
# ---------------------------------------------------------------------------


class TestGetProjectById:
    async def test_returns_project_for_valid_id(self, db):
        await _insert("get-by-id")
        result = await _repo(ADMIN).get_one({"id": "get-by-id"}, fields=None)
        assert result is not None
        assert result.id == "get-by-id"

    async def test_returns_none_for_missing_id(self, db):
        result = await _repo(ADMIN).get_one({"id": "does-not-exist"}, fields=None)
        assert result is None

    async def test_admin_can_get_private_project(self, db):
        await _insert("get-priv", is_public=False)
        result = await _repo(ADMIN).get_one({"id": "get-priv"}, fields=None)
        assert result is not None

    async def test_anon_cannot_get_private_project(self, db):
        await _insert("get-priv-anon", is_public=False)
        result = await _repo(ANON).get_one({"id": "get-priv-anon"}, fields=None)
        assert result is None


# ---------------------------------------------------------------------------
# get_many — id filtering
#
# Regression: Beanie stores the primary key under Mongo's ``_id`` (``id`` is an
# alias), but fastapi-filter keys queries on the raw field name. Without the
# ``id`` -> ``_id`` remap in BaseFilter these filters matched nothing even
# though get_one (which queries ``_id`` directly) found the document.
# ---------------------------------------------------------------------------


class TestGetProjectsIdFilter:
    async def test_filter_by_id_matches(self, db):
        from mpcontribs_api.domains.projects.models import ProjectFilter

        await _insert("filter-id-hit")
        page = await _repo(ADMIN).get_many(
            filter=ProjectFilter(id="filter-id-hit"), pagination=CursorParams(), fields=None
        )
        assert {p.id for p in page.items} == {"filter-id-hit"}

    async def test_filter_by_id_in_matches(self, db):
        from mpcontribs_api.domains.projects.models import ProjectFilter

        await _insert("filter-id-in-a")
        await _insert("filter-id-in-b")
        await _insert("filter-id-in-c")
        page = await _repo(ADMIN).get_many(
            filter=ProjectFilter(id__in=["filter-id-in-a", "filter-id-in-b"]),
            pagination=CursorParams(),
            fields=None,
        )
        assert {p.id for p in page.items} == {"filter-id-in-a", "filter-id-in-b"}

    async def test_filter_by_id_neq_excludes(self, db):
        from mpcontribs_api.domains.projects.models import ProjectFilter

        await _insert("filter-id-neq-keep")
        await _insert("filter-id-neq-drop")
        page = await _repo(ADMIN).get_many(
            filter=ProjectFilter(id__neq="filter-id-neq-drop"), pagination=CursorParams(), fields=None
        )
        ids = {p.id for p in page.items}
        assert "filter-id-neq-keep" in ids
        assert "filter-id-neq-drop" not in ids


# ---------------------------------------------------------------------------
# get_many — tags filtering
#
# ``tags__contains`` maps to MongoDB ``$all``: a project matches only when its
# tags are a superset of every value supplied (the query list is a subset of
# the stored array). Contrast with ``tags__in`` ($in), which matches on any
# single overlapping tag.
# ---------------------------------------------------------------------------


class TestGetProjectsTagsFilter:
    async def test_contains_requires_all_tags_as_subset(self, db):
        from mpcontribs_api.domains.projects.models import ProjectFilter

        await _insert("tags-superset", tags=["alpha", "beta", "gamma"])
        await _insert("tags-partial", tags=["alpha", "beta"])
        await _insert("tags-none", tags=["delta"])
        page = await _repo(ADMIN).get_many(
            filter=ProjectFilter(tags__contains=["alpha", "gamma"]),
            pagination=CursorParams(),
            fields=None,
        )
        assert {p.id for p in page.items} == {"tags-superset"}

    async def test_contains_single_tag(self, db):
        from mpcontribs_api.domains.projects.models import ProjectFilter

        await _insert("tags-single-hit", tags=["alpha", "beta"])
        await _insert("tags-single-miss", tags=["beta", "gamma"])
        page = await _repo(ADMIN).get_many(
            filter=ProjectFilter(tags__contains=["alpha"]),
            pagination=CursorParams(),
            fields=None,
        )
        assert {p.id for p in page.items} == {"tags-single-hit"}

    async def test_contains_parses_comma_string(self, db):
        from mpcontribs_api.domains.projects.models import ProjectFilter

        await _insert("tags-csv-hit", tags=["alpha", "beta", "gamma"])
        await _insert("tags-csv-miss", tags=["alpha"])
        # FilterDepends collapses the list query param to a comma string; the
        # BaseFilter validator must re-expand it.
        page = await _repo(ADMIN).get_many(
            filter=ProjectFilter(tags__contains="alpha,beta"),
            pagination=CursorParams(),
            fields=None,
        )
        assert {p.id for p in page.items} == {"tags-csv-hit"}


# ---------------------------------------------------------------------------
# Field projection
# ---------------------------------------------------------------------------


class TestFieldProjection:
    async def test_projection_returns_only_requested_fields(self, db):
        await _insert("proj-fields", is_public=True, is_approved=True)
        fields = ProjectOut.parse_fields(["title"])
        page = await _repo(ADMIN).get_many(filter=_noop_filter(), pagination=CursorParams(), fields=fields)
        assert len(page.items) == 1
        item = page.items[0]
        assert item.title == "proj-fields"
        # authors was not requested — absent from the projected model entirely
        assert not hasattr(item, "authors")

    async def test_no_projection_returns_all_fields(self, db):
        await _insert("proj-all", is_public=True, is_approved=True)
        page = await _repo(ADMIN).get_many(filter=_noop_filter(), pagination=CursorParams(), fields=None)
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
        page = await _repo(ADMIN).get_many(filter=_noop_filter(), pagination=CursorParams(limit=3), fields=None)
        assert len(page.items) == 3

    async def test_next_cursor_set_when_more_items(self, db):
        for i in range(4):
            await _insert(f"pag-cursor-{i:02d}", is_public=True, is_approved=True)
        page = await _repo(ADMIN).get_many(filter=_noop_filter(), pagination=CursorParams(limit=2), fields=None)
        assert page.next_cursor is not None

    async def test_next_cursor_none_on_last_page(self, db):
        for i in range(3):
            await _insert(f"pag-last-{i:02d}", is_public=True, is_approved=True)
        page = await _repo(ADMIN).get_many(filter=_noop_filter(), pagination=CursorParams(limit=10), fields=None)
        assert page.next_cursor is None

    async def test_cursor_fetches_next_page(self, db):
        for i in range(4):
            await _insert(f"pag-next-{i:02d}", is_public=True, is_approved=True)
        page1 = await _repo(ADMIN).get_many(filter=_noop_filter(), pagination=CursorParams(limit=2), fields=None)
        assert page1.next_cursor is not None
        page2 = await _repo(ADMIN).get_many(
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
            page = await _repo(ADMIN).get_many(
                filter=_noop_filter(), pagination=CursorParams(limit=2, cursor=cursor), fields=None
            )
            all_ids.update(p.id for p in page.items)
            cursor = page.next_cursor
            if cursor is None:
                break
        assert all(f"pag-all-{i:02d}" in all_ids for i in range(5))


# ---------------------------------------------------------------------------
# patch_one  (base mechanics: scoped $set; policy lives in the service)
# ---------------------------------------------------------------------------


class TestPatchProject:
    async def test_updates_single_field(self, db):
        await _insert("patch-me")
        await _repo(ADMIN).patch_one({"id": "patch-me"}, ProjectPatch(title="Updated Title"))
        found = await Project.find_one(Project.id == "patch-me")
        assert found.title == "Updated Title"

    async def test_unset_fields_not_overwritten(self, db):
        await _insert("patch-preserve")
        original = await Project.find_one(Project.id == "patch-preserve")
        await _repo(ADMIN).patch_one({"id": "patch-preserve"}, ProjectPatch(title="New Title"))
        found = await Project.find_one(Project.id == "patch-preserve")
        assert found.authors == original.authors

    async def test_not_found_raises(self, db):
        with pytest.raises(NotFoundError):
            await _repo(ADMIN).patch_one({"id": "no-such-id"}, ProjectPatch(title="Won't work"))

    async def test_empty_patch_returns_existing(self, db):
        await _insert("patch-empty")
        result = await _repo(ADMIN).patch_one({"id": "patch-empty"}, ProjectPatch())
        assert result.id == "patch-empty"


# ---------------------------------------------------------------------------
# delete_one  (base mechanics: scoped delete; owner-or-admin gate lives in the service)
# ---------------------------------------------------------------------------


class TestDeleteProject:
    async def test_deleted_project_not_in_default_query(self, db):
        await _insert("del-me", is_public=True, is_approved=True)
        await _repo(ADMIN).delete_one({"id": "del-me"})
        page = await _repo(ADMIN).get_many(filter=_noop_filter(), pagination=CursorParams(), fields=None)
        assert "del-me" not in {p.id for p in page.items}

    async def test_delete_nonexistent_throws_error(self, db):
        with pytest.raises(NotFoundError, match="not found"):
            await _repo(ADMIN).delete_one({"id": "ghost-id"})


# ---------------------------------------------------------------------------
# Toolbox query/persistence primitives the service composes
# ---------------------------------------------------------------------------


class TestToolboxPrimitives:
    async def test_count_for_owner_counts_only_that_owner(self, db):
        await _insert("cbo-a", owner=ALICE_EMAIL)
        await _insert("cbo-b", owner=ALICE_EMAIL)
        await _insert("cbo-c", owner=BOB_EMAIL)
        assert await _repo(ADMIN).count_for_owner(ALICE_EMAIL) == 2
        assert await _repo(ADMIN).count_for_owner(BOB_EMAIL) == 1

    async def test_count_for_owner_is_unscoped(self, db):
        # The count is a property of the owner, independent of who asks — even a caller who cannot
        # see the private projects sees the true total.
        await _insert("cbo-priv-1", owner=ALICE_EMAIL, is_public=False)
        await _insert("cbo-priv-2", owner=ALICE_EMAIL, is_public=False)
        assert await _repo(BOB).count_for_owner(ALICE_EMAIL) == 2

    async def test_find_by_id_unscoped_ignores_visibility(self, db):
        await _insert("fbi-hidden", owner=ALICE_EMAIL, is_public=False)
        # BOB cannot *see* it via scope, but the unscoped existence lookup still resolves it.
        found = await _repo(BOB).find_by_id_unscoped("fbi-hidden")
        assert found is not None
        assert found.id == "fbi-hidden"

    async def test_find_by_id_unscoped_returns_none_when_absent(self, db):
        assert await _repo(ADMIN).find_by_id_unscoped("fbi-missing") is None

    async def test_save_inserts_then_replaces(self, db):
        doc = Project.from_input_model(_project_in("save-doc", title="First"), id="save-doc")
        await _repo(ADMIN).save(doc)
        assert (await Project.find_one(Project.id == "save-doc")).title == "First"
        # Saving the same id again replaces in place (upsert semantics).
        doc.title = "Second"
        await _repo(ADMIN).save(doc)
        assert (await Project.find_one(Project.id == "save-doc")).title == "Second"
