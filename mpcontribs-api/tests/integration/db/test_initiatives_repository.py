"""Real-DB tests for :class:`InitiativeRepository` as a query/persistence toolbox.

Authorization (authenticated-create, manage-rights, admin-only approval, owner-or-admin delete), the
``public ⇒ approved`` invariant, and the per-owner unapproved quota moved to
:class:`InitiativeService` (see ``test_initiatives_service.py``). What remains here is the toolbox:
scoped reads (visibility, filters), the mechanical ``insert`` (owner-stamp + dup-slug reject), and
``count_unapproved_for_owner``. State-seeding uses the base ``patch_one`` (a mechanical ``$set`` with
no auth), which the repo no longer overrides.
"""

import pytest

from mpcontribs_api.authz import User
from mpcontribs_api.domains.initiatives.models import (
    Initiative,
    InitiativeFilter,
    InitiativeIn,
    InitiativePatch,
)
from mpcontribs_api.domains.initiatives.repository import InitiativeRepository
from mpcontribs_api.exceptions import ConflictError
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
    """Seed via the repository's mechanical insert (owner passed explicitly, as the service would)."""
    return await _repo(owner_user).insert_one(InitiativeIn(slug=slug, name=name), owner=owner_user.username)


async def _publish(slug: str) -> None:
    """Mark ``slug`` approved+public via the base (mechanical, no-auth) patch — for scope seeding."""
    await _repo(ADMIN).patch_one({"slug": slug}, InitiativePatch(is_approved=True, is_public=True))


# ---------------------------------------------------------------------------
# insert (mechanical: owner-stamp + dup-slug reject)
# ---------------------------------------------------------------------------


class TestInsert:
    async def test_stamps_owner_and_starts_private_unapproved(self, db):
        created = await _insert("battery-genome", ALICE)
        assert created.owner == ALICE_EMAIL
        assert created.is_public is False
        assert created.is_approved is False

    async def test_duplicate_slug_is_conflict(self, db):
        await _insert("dup-slug", ALICE)
        with pytest.raises(ConflictError):
            await _insert("dup-slug", BOB)  # globally unique, even across owners


# ---------------------------------------------------------------------------
# count_unapproved_for_owner  (toolbox primitive; the cap decision lives in the service)
# ---------------------------------------------------------------------------


class TestCountUnapprovedForOwner:
    async def test_counts_only_unapproved_of_that_owner(self, db):
        await _insert("cnt-a", ALICE)
        await _insert("cnt-b", ALICE)
        await _insert("cnt-bob", BOB)
        await _publish("cnt-a")  # approved no longer counts
        assert await _repo(ADMIN).count_unapproved_for_owner(ALICE_EMAIL) == 1
        assert await _repo(ADMIN).count_unapproved_for_owner(BOB_EMAIL) == 1

    async def test_is_unscoped(self, db):
        # The count is the owner's true total, independent of who asks (Bob cannot see Alice's).
        await _insert("cnt-priv-1", ALICE)
        await _insert("cnt-priv-2", ALICE)
        assert await _repo(BOB).count_unapproved_for_owner(ALICE_EMAIL) == 2


# ---------------------------------------------------------------------------
# Read scope (visibility)
# ---------------------------------------------------------------------------


class TestReadScope:
    async def test_private_unapproved_visibility(self, db):
        await _insert("scoped-priv", ALICE)
        assert await _repo(ALICE).get_one({"slug": "scoped-priv"}, fields=None) is not None  # owner
        assert await _repo(ADMIN).get_one({"slug": "scoped-priv"}, fields=None) is not None  # admin
        assert await _repo(_collaborator("scoped-priv")).get_one({"slug": "scoped-priv"}, fields=None) is not None
        assert await _repo(ANON).get_one({"slug": "scoped-priv"}, fields=None) is None  # anon
        assert await _repo(BOB).get_one({"slug": "scoped-priv"}, fields=None) is None  # unrelated user

    async def test_public_approved_visible_to_anon(self, db):
        await _insert("scoped-pub", ALICE)
        await _publish("scoped-pub")
        assert await _repo(ANON).get_one({"slug": "scoped-pub"}, fields=None) is not None


# ---------------------------------------------------------------------------
# Listing + filtering (scoped)
# ---------------------------------------------------------------------------


class TestListAndFilter:
    async def test_list_scoped_to_caller(self, db):
        await _insert("mine-1", ALICE)
        await _insert("bobs-1", BOB)  # Bob's private initiative, invisible to Alice
        page = await _repo(ALICE).get_many(CursorParams(), InitiativeFilter(), fields=None)
        slugs = {i.slug for i in page.items}
        assert "mine-1" in slugs
        assert "bobs-1" not in slugs

    async def test_filter_by_is_approved(self, db):
        await _insert("appr-1", ALICE)
        await _insert("unappr-1", ALICE)
        await _publish("appr-1")
        page = await _repo(ADMIN).get_many(CursorParams(), InitiativeFilter(is_approved=True), fields=None)
        slugs = {i.slug for i in page.items}
        assert "appr-1" in slugs
        assert "unappr-1" not in slugs

    async def test_filter_by_owner(self, db):
        await _insert("owned-alice", ALICE)
        await _insert("owned-bob", BOB)
        page = await _repo(ADMIN).get_many(CursorParams(), InitiativeFilter(owner=BOB_EMAIL), fields=None)
        assert {i.slug for i in page.items} == {"owned-bob"}
