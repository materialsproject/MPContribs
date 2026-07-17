import pytest

from mpcontribs_api.authz import User
from mpcontribs_api.config import get_settings
from mpcontribs_api.domains.initiatives.models import (
    Initiative,
    InitiativeFilter,
    InitiativeIn,
    InitiativePatch,
)
from mpcontribs_api.domains.initiatives.repository import InitiativeRepository
from mpcontribs_api.exceptions import ConflictError, NotFoundError, PermissionError, ValidationError
from mpcontribs_api.pagination import CursorParams

# Share the session event loop (see the projects repo test for why).
pytestmark = [pytest.mark.db, pytest.mark.asyncio(loop_scope="session")]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ADMIN = User(username="google:admin@example.com", groups=frozenset({"admin"}))
ALICE = User(username="google:alice@example.com", groups=frozenset({"mp-team"}))
BOB = User(username="google:bob@example.com", groups=frozenset({"mp-team"}))
ANON = User()

ALICE_EMAIL = "google:alice@example.com"
BOB_EMAIL = "google:bob@example.com"


def _repo(user: User) -> InitiativeRepository:
    return InitiativeRepository(user)


def _collaborator(slug: str, username: str = BOB_EMAIL) -> User:
    """A user whose role grants them collaborator rights on ``slug``."""
    return User(username=username, groups=frozenset({f"initiative:{slug}"}))


async def _insert(slug: str, owner_user: User = ALICE, name: str = "An Initiative") -> Initiative:
    return await _repo(owner_user).insert_initiative(InitiativeIn(slug=slug, name=name))


async def _approve(slug: str) -> Initiative:
    return await _repo(ADMIN).patch_initiative(slug, InitiativePatch(is_approved=True))


# ---------------------------------------------------------------------------
# Create + owner forcing
# ---------------------------------------------------------------------------


class TestInsert:
    async def test_forces_owner_and_starts_private_unapproved(self, db):
        created = await _insert("battery-genome", ALICE)
        assert created.owner == ALICE_EMAIL
        assert created.is_public is False
        assert created.is_approved is False

    async def test_duplicate_slug_is_conflict(self, db):
        await _insert("dup-slug", ALICE)
        with pytest.raises(ConflictError):
            await _insert("dup-slug", BOB)  # globally unique, even across owners

    async def test_anonymous_cannot_create(self, db):
        with pytest.raises(PermissionError):
            await _repo(ANON).insert_initiative(InitiativeIn(slug="anon-init", name="x"))

    async def test_invalid_slug_rejected(self, db):
        with pytest.raises(ValidationError):
            InitiativeIn(slug="Not A Slug!", name="x")


class TestUnapprovedPerOwnerLimit:
    async def test_owner_capped_at_configured_unapproved(self, db):
        limit = get_settings().domain.initiatives.max_unapproved_per_owner
        for i in range(limit):
            await _insert(f"cap-{i}", ALICE)
        with pytest.raises(ConflictError):
            await _insert("cap-over", ALICE)

    async def test_approved_do_not_count_against_quota(self, db):
        limit = get_settings().domain.initiatives.max_unapproved_per_owner
        for i in range(limit):
            await _insert(f"quota-{i}", ALICE)
        await _approve("quota-0")  # frees a slot
        # A fresh unapproved initiative now fits again.
        assert await _insert("quota-extra", ALICE) is not None

    async def test_admin_is_exempt(self, db):
        limit = get_settings().domain.initiatives.max_unapproved_per_owner
        for i in range(limit + 2):
            await _repo(ADMIN).insert_initiative(InitiativeIn(slug=f"admin-{i}", name="x"))


# ---------------------------------------------------------------------------
# Approval + public invariant
# ---------------------------------------------------------------------------


class TestApprovalAndPublic:
    async def test_only_admin_may_approve(self, db):
        await _insert("approve-me", ALICE)
        with pytest.raises(PermissionError):
            await _repo(ALICE).patch_initiative("approve-me", InitiativePatch(is_approved=True))
        approved = await _approve("approve-me")
        assert approved.is_approved is True

    async def test_cannot_make_public_while_unapproved(self, db):
        await _insert("public-fail", ALICE)
        with pytest.raises(ValidationError):
            await _repo(ALICE).patch_initiative("public-fail", InitiativePatch(is_public=True))

    async def test_public_allowed_once_approved(self, db):
        await _insert("public-ok", ALICE)
        await _approve("public-ok")
        patched = await _repo(ALICE).patch_initiative("public-ok", InitiativePatch(is_public=True))
        assert patched.is_public is True

    async def test_admin_can_approve_and_publish_together(self, db):
        await _insert("publish-both", ALICE)
        patched = await _repo(ADMIN).patch_initiative(
            "publish-both", InitiativePatch(is_approved=True, is_public=True)
        )
        assert patched.is_approved is True and patched.is_public is True


# ---------------------------------------------------------------------------
# Manage rights (patch) + read scope
# ---------------------------------------------------------------------------


class TestManageAndScope:
    async def test_owner_can_rename(self, db):
        await _insert("rename-me", ALICE)
        patched = await _repo(ALICE).patch_initiative("rename-me", InitiativePatch(name="Renamed"))
        assert patched.name == "Renamed"

    async def test_collaborator_can_patch(self, db):
        await _insert("collab-patch", ALICE)
        patched = await _repo(_collaborator("collab-patch")).patch_initiative(
            "collab-patch", InitiativePatch(name="By Collaborator")
        )
        assert patched.name == "By Collaborator"

    async def test_visible_but_unmanaged_cannot_patch(self, db):
        # An approved+public initiative is visible to everyone, but a stranger still cannot manage it.
        await _insert("visible-public", ALICE)
        await _approve("visible-public")
        await _repo(ALICE).patch_initiative("visible-public", InitiativePatch(is_public=True))
        stranger = User(username="google:carol@example.com", groups=frozenset())
        with pytest.raises(PermissionError):
            await _repo(stranger).patch_initiative("visible-public", InitiativePatch(name="hijack"))

    async def test_private_unapproved_scope(self, db):
        await _insert("scoped-priv", ALICE)
        assert await _repo(ALICE).get_initiative("scoped-priv", fields=None) is not None  # owner
        assert await _repo(ADMIN).get_initiative("scoped-priv", fields=None) is not None  # admin
        assert await _repo(_collaborator("scoped-priv")).get_initiative("scoped-priv", fields=None) is not None
        assert await _repo(ANON).get_initiative("scoped-priv", fields=None) is None  # anon
        assert await _repo(BOB).get_initiative("scoped-priv", fields=None) is None  # unrelated user

    async def test_public_approved_visible_to_anon(self, db):
        await _insert("scoped-pub", ALICE)
        await _approve("scoped-pub")
        await _repo(ALICE).patch_initiative("scoped-pub", InitiativePatch(is_public=True))
        assert await _repo(ANON).get_initiative("scoped-pub", fields=None) is not None


# ---------------------------------------------------------------------------
# Delete (owner or admin only)
# ---------------------------------------------------------------------------


class TestDelete:
    async def test_owner_can_delete(self, db):
        await _insert("del-owner", ALICE)
        result = await _repo(ALICE).delete_initiative("del-owner")
        assert result.num_deleted == 1
        assert await _repo(ADMIN).get_initiative("del-owner", fields=None) is None

    async def test_collaborator_cannot_delete(self, db):
        await _insert("del-collab", ALICE)
        with pytest.raises(PermissionError):
            await _repo(_collaborator("del-collab")).delete_initiative("del-collab")

    async def test_missing_is_not_found(self, db):
        with pytest.raises(NotFoundError):
            await _repo(ADMIN).delete_initiative("nope-missing")


# ---------------------------------------------------------------------------
# Listing + filtering (scoped)
# ---------------------------------------------------------------------------


class TestListAndFilter:
    async def test_list_scoped_to_caller(self, db):
        await _insert("mine-1", ALICE)
        await _insert("bobs-1", BOB)  # Bob's private initiative, invisible to Alice
        page = await _repo(ALICE).get_initiatives(CursorParams(), InitiativeFilter(), fields=None)
        slugs = {i.slug for i in page.items}
        assert "mine-1" in slugs
        assert "bobs-1" not in slugs

    async def test_filter_by_is_approved(self, db):
        await _insert("appr-1", ALICE)
        await _insert("unappr-1", ALICE)
        await _approve("appr-1")
        page = await _repo(ADMIN).get_initiatives(CursorParams(), InitiativeFilter(is_approved=True), fields=None)
        slugs = {i.slug for i in page.items}
        assert "appr-1" in slugs
        assert "unappr-1" not in slugs

    async def test_filter_by_owner(self, db):
        await _insert("owned-alice", ALICE)
        await _insert("owned-bob", BOB)
        page = await _repo(ADMIN).get_initiatives(CursorParams(), InitiativeFilter(owner=BOB_EMAIL), fields=None)
        assert {i.slug for i in page.items} == {"owned-bob"}


# ---------------------------------------------------------------------------
# Admin bypass
# ---------------------------------------------------------------------------


class TestAdminBypass:
    async def test_admin_can_patch_non_owned(self, db):
        await _insert("admin-patch", ALICE)
        patched = await _repo(ADMIN).patch_initiative("admin-patch", InitiativePatch(name="Admin Renamed"))
        assert patched.name == "Admin Renamed"

    async def test_admin_can_delete_non_owned(self, db):
        await _insert("admin-del", ALICE)
        result = await _repo(ADMIN).delete_initiative("admin-del")
        assert result.num_deleted == 1
