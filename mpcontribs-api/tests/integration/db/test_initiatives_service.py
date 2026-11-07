import pytest
from beanie import Link
from bson import DBRef

from mpcontribs_api.authz import User
from mpcontribs_api.config import get_settings
from mpcontribs_api.domains.initiatives.models import Initiative, InitiativeFilter, InitiativeIn, InitiativePatch
from mpcontribs_api.domains.initiatives.repository import MongoDbInitiativeRepository
from mpcontribs_api.domains.initiatives.service import InitiativeService
from mpcontribs_api.domains.projects.models import Project
from mpcontribs_api.domains.projects.repository import MongoDbProjectRepository
from mpcontribs_api.exceptions import ConflictError, NotFoundError, PermissionError, ValidationError
from mpcontribs_api.pagination import CursorParams

pytestmark = [pytest.mark.db, pytest.mark.asyncio(loop_scope="session")]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ADMIN = User(username="google:admin@example.com", groups=frozenset({"admin"}))
ALICE = User(username="google:alice@example.com", groups=frozenset({"mp-team"}))
CAROL = User(username="google:carol@example.com", groups=frozenset())

ALICE_EMAIL = "google:alice@example.com"
BOB_EMAIL = "google:bob@example.com"
CAROL_EMAIL = "google:carol@example.com"


def _collaborator(slug: str, username: str = BOB_EMAIL) -> User:
    return User(username=username, groups=[f"mpcontribs:initiatives/{slug}=owner"])


async def _insert_project(pid: str, owner: str = ALICE_EMAIL, initiative_id=None) -> Project:
    """Seed a project directly. Projects are worker-written now, so build the stored document by hand;
    ``initiative_id`` optionally seeds the initiative back-reference the worker would have set."""
    document = Project(
        _id=pid,
        title=pid[:30],
        authors="Author",
        description="desc",
        owner=owner,
        initiative=Link(DBRef("initiatives", initiative_id), Initiative) if initiative_id is not None else None,
    )
    return await MongoDbProjectRepository(ADMIN).insert_one(document)


async def _insert_initiative(slug: str, owner_user: User = ALICE):
    document = Initiative.from_input_model(InitiativeIn(slug=slug, name="Init"), owner=owner_user.username)
    return await MongoDbInitiativeRepository(owner_user).insert_one(document)


def _assigned_id(project: Project):
    """The initiative _id a returned project points at, or None."""
    link = project.initiative
    if link is None:
        return None
    return link.ref.id if isinstance(link, Link) else link.id


# ===========================================================================
# InitiativeService — create / patch / delete authorization
#
# The initiative write policy (authenticated-create, per-owner unapproved quota, manage rights,
# admin-only approval, public⇒approved, owner-or-admin delete) lives on InitiativeService; these
# drive it against the real DB. Initiative<->project *assignment* no longer lives in the API
# (projects are read-only; assignment is deferred to the upload worker), so those tests are gone —
# only the back-reference cleanup on initiative delete remains below.
# ===========================================================================


def _initiative_service(user: User) -> InitiativeService:
    return InitiativeService(
        user=user, initiatives=MongoDbInitiativeRepository(user), projects=MongoDbProjectRepository(user)
    )


async def _approve(slug: str) -> Initiative:
    return await _initiative_service(ADMIN).update_one({"slug": slug}, InitiativePatch(is_approved=True))


class TestInitiativeCreate:
    async def test_forces_owner_and_starts_private_unapproved(self, db):
        created = await _initiative_service(ALICE).insert_one(InitiativeIn(slug="svc-create", name="X"))
        assert created.owner == ALICE_EMAIL
        assert created.is_public is False
        assert created.is_approved is False

    async def test_anonymous_cannot_create(self, db):
        with pytest.raises(PermissionError):
            await _initiative_service(User()).insert_one(InitiativeIn(slug="svc-anon", name="X"))

    async def test_duplicate_slug_is_conflict(self, db):
        await _initiative_service(ALICE).insert_one(InitiativeIn(slug="svc-dup", name="X"))
        bob = User(username=BOB_EMAIL, groups=frozenset())
        with pytest.raises(ConflictError):
            await _initiative_service(bob).insert_one(InitiativeIn(slug="svc-dup", name="X"))

    async def test_owner_capped_at_configured_unapproved(self, db):
        limit = get_settings().consumer.initiative.max_unapproved_per_owner
        for i in range(limit):
            await _initiative_service(ALICE).insert_one(InitiativeIn(slug=f"svc-cap-{i}", name="X"))
        with pytest.raises(ConflictError):
            await _initiative_service(ALICE).insert_one(InitiativeIn(slug="svc-cap-over", name="X"))

    async def test_approved_frees_a_quota_slot(self, db):
        limit = get_settings().consumer.initiative.max_unapproved_per_owner
        for i in range(limit):
            await _initiative_service(ALICE).insert_one(InitiativeIn(slug=f"svc-quota-{i}", name="X"))
        await _approve("svc-quota-0")
        assert await _initiative_service(ALICE).insert_one(InitiativeIn(slug="svc-quota-extra", name="X")) is not None

    async def test_admin_is_exempt_from_quota(self, db):
        limit = get_settings().consumer.initiative.max_unapproved_per_owner
        for i in range(limit + 2):
            await _initiative_service(ADMIN).insert_one(InitiativeIn(slug=f"svc-admin-{i}", name="X"))


class TestInitiativePatchAuth:
    async def test_only_admin_may_approve(self, db):
        await _insert_initiative("svc-approve", ALICE)
        with pytest.raises(PermissionError):
            await _initiative_service(ALICE).update_one({"slug": "svc-approve"}, InitiativePatch(is_approved=True))
        approved = await _approve("svc-approve")
        assert approved.is_approved is True

    async def test_cannot_make_public_while_unapproved(self, db):
        await _insert_initiative("svc-pub-fail", ALICE)
        with pytest.raises(ValidationError):
            await _initiative_service(ALICE).update_one({"slug": "svc-pub-fail"}, InitiativePatch(is_public=True))

    async def test_public_allowed_once_approved(self, db):
        await _insert_initiative("svc-pub-ok", ALICE)
        await _approve("svc-pub-ok")
        patched = await _initiative_service(ALICE).update_one({"slug": "svc-pub-ok"}, InitiativePatch(is_public=True))
        assert patched.is_public is True

    async def test_owner_can_rename(self, db):
        await _insert_initiative("svc-rename", ALICE)
        patched = await _initiative_service(ALICE).update_one({"slug": "svc-rename"}, InitiativePatch(name="Renamed"))
        assert patched.name == "Renamed"

    async def test_collaborator_can_patch(self, db):
        await _insert_initiative("svc-collab", ALICE)
        patched = await _initiative_service(_collaborator("svc-collab")).update_one(
            {"slug": "svc-collab"}, InitiativePatch(name="By Collaborator")
        )
        assert patched.name == "By Collaborator"

    async def test_visible_but_unmanaged_cannot_patch(self, db):
        await _insert_initiative("svc-visible", ALICE)
        await _initiative_service(ADMIN).update_one(
            {"slug": "svc-visible"}, InitiativePatch(is_approved=True, is_public=True)
        )
        stranger = User(username=CAROL_EMAIL, groups=frozenset())
        with pytest.raises(PermissionError):
            await _initiative_service(stranger).update_one({"slug": "svc-visible"}, InitiativePatch(name="hijack"))

    async def test_missing_is_not_found(self, db):
        with pytest.raises(NotFoundError):
            await _initiative_service(ADMIN).update_one({"slug": "svc-patch-ghost"}, InitiativePatch(name="x"))

    async def test_admin_can_patch_non_owned(self, db):
        await _insert_initiative("svc-admin-patch", ALICE)
        patched = await _initiative_service(ADMIN).update_one(
            {"slug": "svc-admin-patch"}, InitiativePatch(name="Admin Renamed")
        )
        assert patched.name == "Admin Renamed"


class TestInitiativeDelete:
    async def test_owner_can_delete(self, db):
        await _insert_initiative("svc-del-owner", ALICE)
        result = await _initiative_service(ALICE).delete_one({"slug": "svc-del-owner"})
        assert result.num_deleted == 1

    async def test_collaborator_cannot_delete(self, db):
        await _insert_initiative("svc-del-collab", ALICE)
        with pytest.raises(PermissionError):
            await _initiative_service(_collaborator("svc-del-collab")).delete_one({"slug": "svc-del-collab"})

    async def test_missing_is_not_found(self, db):
        with pytest.raises(NotFoundError):
            await _initiative_service(ADMIN).delete_one({"slug": "svc-del-ghost"})

    async def test_admin_can_delete_non_owned(self, db):
        await _insert_initiative("svc-admin-del", ALICE)
        result = await _initiative_service(ADMIN).delete_one({"slug": "svc-admin-del"})
        assert result.num_deleted == 1

    async def test_delete_clears_member_project_links(self, db):
        # Deleting an initiative must unset the `initiative` link on its members, leaving no
        # dangling reference behind (round-trip: seed a linked project, delete, re-read from the DB).
        init = await _insert_initiative("svc-del-refs", ALICE)
        await _insert_project("del-refs-proj", owner=ALICE_EMAIL, initiative_id=init.id)

        await _initiative_service(ALICE).delete_one({"slug": "svc-del-refs"})

        reloaded = await Project.find_one(Project.id == "del-refs-proj")
        assert reloaded is not None
        assert _assigned_id(reloaded) is None


# ---------------------------------------------------------------------------
# Read scope — read_many / read_one filter by visibility; out-of-scope writes 404
# ---------------------------------------------------------------------------


class TestInitiativeReadScope:
    async def test_get_many_hides_private_unowned(self, db):
        # A stranger (no roles) sees only public+approved initiatives, never Alice's private one.
        await _insert_initiative("scope-priv", ALICE)
        await _insert_initiative("scope-pub", ALICE)
        await _approve("scope-pub")
        await _initiative_service(ADMIN).update_one({"slug": "scope-pub"}, InitiativePatch(is_public=True))
        stranger = User(username=CAROL_EMAIL, groups=frozenset())
        page = await _initiative_service(stranger).read_many(
            filter=InitiativeFilter(), pagination=CursorParams(), fields=None
        )
        slugs = {i.slug for i in page.items}
        assert "scope-pub" in slugs
        assert "scope-priv" not in slugs

    async def test_get_one_private_unowned_returns_none(self, db):
        await _insert_initiative("scope-one-priv", ALICE)
        stranger = User(username=CAROL_EMAIL, groups=frozenset())
        assert await _initiative_service(stranger).read_one({"slug": "scope-one-priv"}, fields=None) is None

    async def test_owner_sees_own_private_initiative(self, db):
        await _insert_initiative("scope-own", ALICE)
        found = await _initiative_service(ALICE).read_one({"slug": "scope-own"}, fields=None)
        assert found is not None and found.slug == "scope-own"


class TestInitiativeOutOfScopeWrites:
    async def test_patch_private_unowned_is_not_found(self, db):
        # A private initiative is invisible to a stranger, so patching it is a 404, not a 403 — the
        # 404-before-403 rule (existence is not leaked to callers who cannot see the resource).
        await _insert_initiative("oos-patch", ALICE)
        stranger = User(username=CAROL_EMAIL, groups=frozenset())
        with pytest.raises(NotFoundError):
            await _initiative_service(stranger).update_one({"slug": "oos-patch"}, InitiativePatch(name="hijack"))

    async def test_delete_private_unowned_is_not_found(self, db):
        await _insert_initiative("oos-del", ALICE)
        stranger = User(username=CAROL_EMAIL, groups=frozenset())
        with pytest.raises(NotFoundError):
            await _initiative_service(stranger).delete_one({"slug": "oos-del"})
