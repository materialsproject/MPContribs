import pytest
from beanie import Link

from mpcontribs_api.authz import User
from mpcontribs_api.config import get_settings
from mpcontribs_api.domains.initiatives.models import Initiative, InitiativeFilter, InitiativeIn, InitiativePatch
from mpcontribs_api.domains.initiatives.repository import MongoDbInitiativeRepository
from mpcontribs_api.domains.initiatives.service import InitiativeService
from mpcontribs_api.domains.projects.models import Project, ProjectIn, ProjectPatch
from mpcontribs_api.domains.projects.repository import MongoDbProjectRepository
from mpcontribs_api.domains.projects.service import ProjectService
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


def _service(user: User) -> ProjectService:
    return ProjectService(
        user=user,
        projects=MongoDbProjectRepository(user),
        initiatives=MongoDbInitiativeRepository(user),
    )


def _collaborator(slug: str, username: str = BOB_EMAIL) -> User:
    return User(username=username, groups=[f"mpcontribs:initiatives/{slug}=owner"])


async def _insert_project(pid: str, owner: str = ALICE_EMAIL) -> Project:
    document = Project.from_input_model(
        ProjectIn(
            title=pid[:30],
            authors="Author",
            description="desc",
            owner=owner,
        ),
        id=pid,
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


# ---------------------------------------------------------------------------
# Happy-path assignment
# ---------------------------------------------------------------------------


class TestAssign:
    async def test_owner_of_both_can_assign(self, db):
        await _insert_project("proj-a", owner=ALICE_EMAIL)
        init = await _insert_initiative("init-a", ALICE)
        updated = await _service(ALICE).update_one({"id": "proj-a"}, ProjectPatch(initiative="init-a"))
        assert _assigned_id(updated) == init.id

    async def test_collaborator_can_assign_own_project(self, db):
        await _insert_project("proj-b", owner=BOB_EMAIL)
        init = await _insert_initiative("init-collab", ALICE)
        bob = _collaborator("init-collab")
        updated = await _service(bob).update_one({"id": "proj-b"}, ProjectPatch(initiative="init-collab"))
        assert _assigned_id(updated) == init.id

    async def test_plain_patch_passes_through_untouched(self, db):
        await _insert_project("proj-plain", owner=ALICE_EMAIL)
        init = await _insert_initiative("init-plain", ALICE)
        await _service(ALICE).update_one({"id": "proj-plain"}, ProjectPatch(initiative="init-plain"))
        # A patch that does not mention `initiative` must not disturb the existing assignment.
        updated = await _service(ALICE).update_one({"id": "proj-plain"}, ProjectPatch(title="new-title"))
        assert updated.title == "new-title"
        assert _assigned_id(updated) == init.id

    async def test_unassign_clears_link(self, db):
        await _insert_project("proj-un", owner=ALICE_EMAIL)
        await _insert_initiative("init-un", ALICE)
        await _service(ALICE).update_one({"id": "proj-un"}, ProjectPatch(initiative="init-un"))
        updated = await _service(ALICE).update_one({"id": "proj-un"}, ProjectPatch(initiative=None))
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
        await MongoDbInitiativeRepository(ADMIN).update_one(
            {"slug": "init-c"}, InitiativePatch(is_approved=True, is_public=True)
        )
        with pytest.raises(PermissionError):
            await _service(CAROL).update_one({"id": "proj-c"}, ProjectPatch(initiative="init-c"))

    async def test_invisible_initiative_is_not_found(self, db):
        # Alice's private initiative is invisible to Carol, so it reads as not-found (not a 403).
        await _insert_project("proj-c2", owner=CAROL_EMAIL)
        await _insert_initiative("init-priv", ALICE)
        with pytest.raises(NotFoundError):
            await _service(CAROL).update_one({"id": "proj-c2"}, ProjectPatch(initiative="init-priv"))

    async def test_manager_without_project_write_rejected(self, db):
        # Alice manages the initiative but cannot see/write Bob's private project.
        await _insert_project("proj-bob", owner=BOB_EMAIL)
        await _insert_initiative("init-d", ALICE)
        with pytest.raises(NotFoundError):
            await _service(ALICE).update_one({"id": "proj-bob"}, ProjectPatch(initiative="init-d"))

    async def test_assign_to_missing_initiative_is_not_found(self, db):
        await _insert_project("proj-ghost", owner=ALICE_EMAIL)
        with pytest.raises(NotFoundError):
            await _service(ALICE).update_one({"id": "proj-ghost"}, ProjectPatch(initiative="ghost-init"))


# ---------------------------------------------------------------------------
# Member cap on unapproved initiatives
# ---------------------------------------------------------------------------


class TestMemberCap:
    async def test_unapproved_capped_at_configured_members(self, db):
        cap = get_settings().domain.initiatives.max_projects_per_unapproved
        await _insert_initiative("init-cap", ALICE)
        for i in range(cap):
            await _insert_project(f"cap-proj-{i}", owner=ALICE_EMAIL)
            await _service(ALICE).update_one({"id": f"cap-proj-{i}"}, ProjectPatch(initiative="init-cap"))
        await _insert_project("cap-proj-over", owner=ALICE_EMAIL)
        with pytest.raises(ConflictError):
            await _service(ALICE).update_one({"id": "cap-proj-over"}, ProjectPatch(initiative="init-cap"))

    async def test_reassigning_existing_member_is_idempotent(self, db):
        cap = get_settings().domain.initiatives.max_projects_per_unapproved
        await _insert_initiative("init-idem", ALICE)
        for i in range(cap):
            await _insert_project(f"idem-proj-{i}", owner=ALICE_EMAIL)
            await _service(ALICE).update_one({"id": f"idem-proj-{i}"}, ProjectPatch(initiative="init-idem"))
        # At the cap, re-assigning a project that is already a member must not trip the limit.
        again = await _service(ALICE).update_one({"id": "idem-proj-0"}, ProjectPatch(initiative="init-idem"))
        assert again.initiative is not None

    async def test_approved_initiative_has_no_member_cap(self, db, monkeypatch):
        cap = get_settings().domain.initiatives.max_projects_per_unapproved
        # Lift the orthogonal per-user project quota so seeding cap+2 owned projects doesn't trip it;
        # this test isolates the *initiative member* cap, not the project-count cap.
        monkeypatch.setattr(get_settings().consumer, "max_projects", cap + 5)
        await _insert_initiative("init-approved", ALICE)
        await MongoDbInitiativeRepository(ADMIN).update_one({"slug": "init-approved"}, InitiativePatch(is_approved=True))
        for i in range(cap + 2):  # comfortably past the unapproved cap
            await _insert_project(f"appr-proj-{i}", owner=ALICE_EMAIL)
            await _service(ALICE).update_one({"id": f"appr-proj-{i}"}, ProjectPatch(initiative="init-approved"))
        initiative_id = (await MongoDbInitiativeRepository(ADMIN).read_one({"slug": "init-approved"})).id  # type: ignore[union-attr]
        count = await MongoDbProjectRepository(ADMIN).count_matching(
            {"initiative.$id": initiative_id}, scoped=False
        )
        assert count == cap + 2


# ---------------------------------------------------------------------------
# Admin bypass + unassignment rights
# ---------------------------------------------------------------------------


class TestAdminAndUnassign:
    async def test_admin_can_assign_to_any_initiative(self, db):
        # Alice's private initiative is manageable by an admin even though the admin holds no role.
        await _insert_project("adm-proj", owner=ALICE_EMAIL)
        init = await _insert_initiative("adm-init", ALICE)
        updated = await _service(ADMIN).update_one({"id": "adm-proj"}, ProjectPatch(initiative="adm-init"))
        assert _assigned_id(updated) == init.id

    async def test_project_owner_can_unassign_without_initiative_rights(self, db):
        # A collaborator assigns Bob's project; Bob, lacking any initiative role, can still detach
        # his own project — unassignment needs only project-write access.
        await _insert_project("detach-proj", owner=BOB_EMAIL)
        await _insert_initiative("detach-init", ALICE)
        await _service(_collaborator("detach-init", username=BOB_EMAIL)).update_one(
            {"id": "detach-proj"}, ProjectPatch(initiative="detach-init")
        )
        bob_plain = User(username=BOB_EMAIL, groups=frozenset())
        updated = await _service(bob_plain).update_one({"id": "detach-proj"}, ProjectPatch(initiative=None))
        assert _assigned_id(updated) is None


# ===========================================================================
# InitiativeService — create / patch / delete authorization
#
# The initiative write policy (authenticated-create, per-owner unapproved quota, manage rights,
# admin-only approval, public⇒approved, owner-or-admin delete) lives on InitiativeService; these
# drive it against the real DB. The ProjectService assignment tests above are a separate concern —
# assignment is an initiative-facing operation on the *project* service.
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
        limit = get_settings().domain.initiatives.max_unapproved_per_owner
        for i in range(limit):
            await _initiative_service(ALICE).insert_one(InitiativeIn(slug=f"svc-cap-{i}", name="X"))
        with pytest.raises(ConflictError):
            await _initiative_service(ALICE).insert_one(InitiativeIn(slug="svc-cap-over", name="X"))

    async def test_approved_frees_a_quota_slot(self, db):
        limit = get_settings().domain.initiatives.max_unapproved_per_owner
        for i in range(limit):
            await _initiative_service(ALICE).insert_one(InitiativeIn(slug=f"svc-quota-{i}", name="X"))
        await _approve("svc-quota-0")
        assert await _initiative_service(ALICE).insert_one(InitiativeIn(slug="svc-quota-extra", name="X")) is not None

    async def test_admin_is_exempt_from_quota(self, db):
        limit = get_settings().domain.initiatives.max_unapproved_per_owner
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
        # dangling reference behind (round-trip: assign, delete, re-read from the DB).
        await _insert_project("del-refs-proj", owner=ALICE_EMAIL)
        init = await _insert_initiative("svc-del-refs", ALICE)
        assigned = await _service(ALICE).update_one({"id": "del-refs-proj"}, ProjectPatch(initiative="svc-del-refs"))
        assert _assigned_id(assigned) == init.id

        await _initiative_service(ALICE).delete_one({"slug": "svc-del-refs"})

        reloaded = await MongoDbProjectRepository(ADMIN).find_by_id_unscoped("del-refs-proj")
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
