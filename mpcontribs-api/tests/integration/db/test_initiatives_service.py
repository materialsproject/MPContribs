import pytest
from beanie import Link

from mpcontribs_api.authz import User
from mpcontribs_api.config import get_settings
from mpcontribs_api.domains.initiatives.models import InitiativeIn, InitiativePatch
from mpcontribs_api.domains.initiatives.repository import InitiativeRepository
from mpcontribs_api.domains.projects.models import Project, ProjectIn, ProjectPatch, Stats
from mpcontribs_api.domains.projects.repository import MongoDbProjectRepository
from mpcontribs_api.domains.projects.service import ProjectInitiativeService
from mpcontribs_api.exceptions import ConflictError, NotFoundError, PermissionError

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
STATS = Stats(columns=0, contributions=0, tables=0, structures=0, attachments=0, size=0.0)


def _service(user: User) -> ProjectInitiativeService:
    return ProjectInitiativeService(
        projects=MongoDbProjectRepository(user),
        initiatives=InitiativeRepository(user),
    )


def _collaborator(slug: str, username: str = BOB_EMAIL) -> User:
    return User(username=username, groups=frozenset({f"initiative:{slug}"}))


async def _insert_project(pid: str, owner: str = ALICE_EMAIL) -> Project:
    return await MongoDbProjectRepository(ADMIN).insert_project(
        ProjectIn(
            _id=pid,
            title=pid[:30],
            authors="Author",
            description="desc",
            owner=owner,
            unique_identifiers=True,
            stats=STATS,
        )
    )


async def _insert_initiative(slug: str, owner_user: User = ALICE):
    return await InitiativeRepository(owner_user).insert_initiative(InitiativeIn(slug=slug, name="Init"))


def _assigned_id(project: Project):
    """The initiative _id a returned project points at, or None."""
    link = project.initiative
    if link is None:
        return None
    return link.ref.id if isinstance(link, Link) else link.id


# ---------------------------------------------------------------------------
# Happy-path assignment
# ---------------------------------------------------------------------------


class TestAssign:
    async def test_owner_of_both_can_assign(self, db):
        await _insert_project("proj-a", owner=ALICE_EMAIL)
        init = await _insert_initiative("init-a", ALICE)
        updated = await _service(ALICE).patch("proj-a", ProjectPatch(initiative="init-a"))
        assert _assigned_id(updated) == init.id

    async def test_collaborator_can_assign_own_project(self, db):
        await _insert_project("proj-b", owner=BOB_EMAIL)
        init = await _insert_initiative("init-collab", ALICE)
        bob = _collaborator("init-collab")
        updated = await _service(bob).patch("proj-b", ProjectPatch(initiative="init-collab"))
        assert _assigned_id(updated) == init.id

    async def test_plain_patch_passes_through_untouched(self, db):
        await _insert_project("proj-plain", owner=ALICE_EMAIL)
        init = await _insert_initiative("init-plain", ALICE)
        await _service(ALICE).patch("proj-plain", ProjectPatch(initiative="init-plain"))
        # A patch that does not mention `initiative` must not disturb the existing assignment.
        updated = await _service(ALICE).patch("proj-plain", ProjectPatch(title="new-title"))
        assert updated.title == "new-title"
        assert _assigned_id(updated) == init.id

    async def test_unassign_clears_link(self, db):
        await _insert_project("proj-un", owner=ALICE_EMAIL)
        await _insert_initiative("init-un", ALICE)
        await _service(ALICE).patch("proj-un", ProjectPatch(initiative="init-un"))
        updated = await _service(ALICE).patch("proj-un", ProjectPatch(initiative=None))
        assert _assigned_id(updated) is None


# ---------------------------------------------------------------------------
# Both-rights enforcement
# ---------------------------------------------------------------------------


class TestBothRights:
    async def test_visible_but_unmanaged_initiative_rejected(self, db):
        # Carol owns her project (project-write ok) and can *see* this public+approved initiative,
        # but she neither owns nor collaborates on it, so she still cannot assign to it.
        await _insert_project("proj-c", owner=CAROL_EMAIL)
        await _insert_initiative("init-c", ALICE)
        await InitiativeRepository(ADMIN).patch_initiative(
            "init-c", InitiativePatch(is_approved=True, is_public=True)
        )
        with pytest.raises(PermissionError):
            await _service(CAROL).patch("proj-c", ProjectPatch(initiative="init-c"))

    async def test_invisible_initiative_is_not_found(self, db):
        # Alice's private initiative is invisible to Carol, so it reads as not-found (not a 403).
        await _insert_project("proj-c2", owner=CAROL_EMAIL)
        await _insert_initiative("init-priv", ALICE)
        with pytest.raises(NotFoundError):
            await _service(CAROL).patch("proj-c2", ProjectPatch(initiative="init-priv"))

    async def test_manager_without_project_write_rejected(self, db):
        # Alice manages the initiative but cannot see/write Bob's private project.
        await _insert_project("proj-bob", owner=BOB_EMAIL)
        await _insert_initiative("init-d", ALICE)
        with pytest.raises(NotFoundError):
            await _service(ALICE).patch("proj-bob", ProjectPatch(initiative="init-d"))

    async def test_assign_to_missing_initiative_is_not_found(self, db):
        await _insert_project("proj-ghost", owner=ALICE_EMAIL)
        with pytest.raises(NotFoundError):
            await _service(ALICE).patch("proj-ghost", ProjectPatch(initiative="ghost-init"))


# ---------------------------------------------------------------------------
# Member cap on unapproved initiatives
# ---------------------------------------------------------------------------


class TestMemberCap:
    async def test_unapproved_capped_at_configured_members(self, db):
        cap = get_settings().initiatives.max_projects_per_unapproved
        await _insert_initiative("init-cap", ALICE)
        for i in range(cap):
            await _insert_project(f"cap-proj-{i}", owner=ALICE_EMAIL)
            await _service(ALICE).patch(f"cap-proj-{i}", ProjectPatch(initiative="init-cap"))
        await _insert_project("cap-proj-over", owner=ALICE_EMAIL)
        with pytest.raises(ConflictError):
            await _service(ALICE).patch("cap-proj-over", ProjectPatch(initiative="init-cap"))

    async def test_reassigning_existing_member_is_idempotent(self, db):
        cap = get_settings().initiatives.max_projects_per_unapproved
        await _insert_initiative("init-idem", ALICE)
        for i in range(cap):
            await _insert_project(f"idem-proj-{i}", owner=ALICE_EMAIL)
            await _service(ALICE).patch(f"idem-proj-{i}", ProjectPatch(initiative="init-idem"))
        # At the cap, re-assigning a project that is already a member must not trip the limit.
        again = await _service(ALICE).patch("idem-proj-0", ProjectPatch(initiative="init-idem"))
        assert again.initiative is not None

    async def test_approved_initiative_has_no_member_cap(self, db):
        cap = get_settings().initiatives.max_projects_per_unapproved
        await _insert_initiative("init-approved", ALICE)
        await InitiativeRepository(ADMIN).patch_initiative("init-approved", InitiativePatch(is_approved=True))
        for i in range(cap + 2):  # comfortably past the unapproved cap
            await _insert_project(f"appr-proj-{i}", owner=ALICE_EMAIL)
            await _service(ALICE).patch(f"appr-proj-{i}", ProjectPatch(initiative="init-approved"))
        count = await MongoDbProjectRepository(ADMIN).count_initiative_members(
            initiative_id=(await InitiativeRepository(ADMIN).resolve_visible("init-approved")).id,  # type: ignore[union-attr]
            exclude_project_id=None,
        )
        assert count == cap + 2
