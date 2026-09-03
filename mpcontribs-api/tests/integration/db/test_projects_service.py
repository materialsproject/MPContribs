import pytest
from beanie import Link

from mpcontribs_api.authz import User
from mpcontribs_api.config import ConsumerLimits, ConsumerProjectLimits
from mpcontribs_api.domains.initiatives.repository import MongoDbInitiativeRepository
from mpcontribs_api.domains.projects.models import Column, Project, ProjectFilter, ProjectIn, ProjectPatch, Stats
from mpcontribs_api.domains.projects.repository import MongoDbProjectRepository
from mpcontribs_api.domains.projects.service import ProjectService
from mpcontribs_api.exceptions import PermissionError as AppPermissionError
from mpcontribs_api.exceptions import ConflictError, NotFoundError, ValidationError
from mpcontribs_api.pagination import CursorParams

pytestmark = [pytest.mark.db, pytest.mark.asyncio(loop_scope="session")]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ADMIN = User(username="google:admin@example.com", groups=frozenset({"admin"}))
ALICE = User(username="google:alice@example.com", groups=frozenset({"mp-team"}))
BOB = User(username="google:bob@example.com", groups=frozenset())
CAROL = User(username="google:carol@example.com", groups=frozenset())

ALICE_EMAIL = "google:alice@example.com"
BOB_EMAIL = "google:bob@example.com"
CAROL_EMAIL = "google:carol@example.com"


def _service(user: User, limits: ConsumerLimits | None = None) -> ProjectService:
    return ProjectService(
        user=user,
        projects=MongoDbProjectRepository(user),
        initiatives=MongoDbInitiativeRepository(user),
        limits=limits,
    )


def _collaborator(slug: str, username: str = BOB_EMAIL) -> User:
    return User(username=username, groups=[f"mpcontribs:initiatives/{slug}=owner"])


def _project_in(id: str, **overrides) -> ProjectIn:
    defaults = {
        "title": id[:30],
        "authors": "Test Author",
        "description": "Test description",
        "owner": ALICE_EMAIL,
    }
    defaults.update(overrides)
    return ProjectIn(**defaults)


async def _insert(id: str, **overrides) -> Project:
    """Seed a project directly through the repository's mechanical insert (admin, no policy)."""
    document = Project.from_input_model(_project_in(id, **overrides), id=id)
    return await MongoDbProjectRepository(ADMIN).insert_one(document)


async def _insert_initiative(slug: str, owner_user: User = ALICE) -> Initiative:
    document = Initiative.from_input_model(InitiativeIn(slug=slug, name="Init"), owner=owner_user.username)
    return await MongoDbInitiativeRepository(owner_user).insert_one(document)


def _assigned_id(project: Project):
    """The initiative _id a returned project points at, or None."""
    link = project.initiative
    if link is None:
        return None
    return link.ref.id if isinstance(link, Link) else link.id


# ---------------------------------------------------------------------------
# delete_one — owner-or-admin, 403 vs 404
# ---------------------------------------------------------------------------


class TestDeleteAuthorization:
    async def test_owner_can_delete_own_project(self, db):
        await _insert("svc-del-own", owner=ALICE_EMAIL)
        await _service(ALICE).delete_one({"id": "svc-del-own"})
        assert await Project.find_one(Project.id == "svc-del-own") is None

    async def test_admin_can_delete_any_project(self, db):
        await _insert("svc-del-admin", owner=ALICE_EMAIL)
        await _service(ADMIN).delete_one({"id": "svc-del-admin"})
        assert await Project.find_one(Project.id == "svc-del-admin") is None

    async def test_group_member_non_owner_cannot_delete(self, db):
        # A user whose group contains the project id can *see* it, but only the owner may delete.
        member = User(username="google:carol@example.com", groups=frozenset({"svc-del-grp"}))
        await _insert("svc-del-grp", owner=ALICE_EMAIL)
        with pytest.raises(AppPermissionError):
            await _service(member).delete_one({"id": "svc-del-grp"})
        assert await Project.find_one(Project.id == "svc-del-grp") is not None

    async def test_visible_public_non_owner_cannot_delete(self, db):
        # BOB can see the public+approved project but does not own it → 403, not a silent success.
        await _insert("svc-del-pub", owner=ALICE_EMAIL, is_public=True, is_approved=True)
        with pytest.raises(AppPermissionError):
            await _service(BOB).delete_one({"id": "svc-del-pub"})
        assert await Project.find_one(Project.id == "svc-del-pub") is not None

    async def test_out_of_scope_delete_not_found(self, db):
        # BOB cannot see Alice's private project → 404 (existence is not leaked as a 403).
        await _insert("svc-del-hidden", owner=ALICE_EMAIL, is_public=False)
        with pytest.raises(NotFoundError):
            await _service(BOB).delete_one({"id": "svc-del-hidden"})
        assert await Project.find_one(Project.id == "svc-del-hidden") is not None


# ---------------------------------------------------------------------------
# update_one — owner-or-admin, 403 vs 404 (mirrors delete_one)
# ---------------------------------------------------------------------------


class TestPatchAuthorization:
    async def test_owner_can_patch_own_project(self, db):
        await _insert("svc-patch-own", owner=ALICE_EMAIL)
        updated = await _service(ALICE).update_one({"id": "svc-patch-own"}, ProjectPatch(title="By Owner"))
        assert updated.title == "By Owner"

    async def test_admin_can_patch_any_project(self, db):
        await _insert("svc-patch-admin", owner=ALICE_EMAIL)
        updated = await _service(ADMIN).update_one({"id": "svc-patch-admin"}, ProjectPatch(title="By Admin"))
        assert updated.title == "By Admin"

    async def test_group_member_non_owner_cannot_patch(self, db):
        # A user whose group grants a role on the project can *see* it, but only the owner may patch.
        member = User(username="google:carol@example.com", groups=frozenset({"svc-patch-grp"}))
        await _insert("svc-patch-grp", owner=ALICE_EMAIL)
        with pytest.raises(AppPermissionError):
            await _service(member).update_one({"id": "svc-patch-grp"}, ProjectPatch(title="Hijacked"))
        doc = await Project.find_one(Project.id == "svc-patch-grp")
        assert doc is not None and doc.title == "svc-patch-grp"[:30]

    async def test_visible_public_non_owner_cannot_patch(self, db):
        # BOB can see the public+approved project but does not own it → 403, and it is left unchanged.
        await _insert("svc-patch-pub", owner=ALICE_EMAIL, is_public=True, is_approved=True)
        with pytest.raises(AppPermissionError):
            await _service(BOB).update_one({"id": "svc-patch-pub"}, ProjectPatch(owner=BOB_EMAIL))
        doc = await Project.find_one(Project.id == "svc-patch-pub")
        assert doc is not None and doc.owner == ALICE_EMAIL

    async def test_out_of_scope_patch_not_found(self, db):
        # BOB cannot see Alice's private project → 404 (existence is not leaked as a 403).
        await _insert("svc-patch-hidden", owner=ALICE_EMAIL, is_public=False)
        with pytest.raises(NotFoundError):
            await _service(BOB).update_one({"id": "svc-patch-hidden"}, ProjectPatch(title="Hijacked"))
        doc = await Project.find_one(Project.id == "svc-patch-hidden")
        assert doc is not None and doc.title == "svc-patch-hidden"[:30]


# ---------------------------------------------------------------------------
# upsert_one — create / update / path-id
# ---------------------------------------------------------------------------


class TestUpsert:
    async def test_upsert_creates_new_project(self, db):
        await _service(ADMIN).upsert_one({"id": "svc-upsert-new"}, data=_project_in("svc-upsert-new"))
        assert await Project.find_one(Project.id == "svc-upsert-new") is not None

    async def test_upsert_updates_existing_project(self, db):
        await _insert("svc-upsert-existing")
        await _service(ADMIN).upsert_one(
            {"id": "svc-upsert-existing"}, data=_project_in("svc-upsert-existing", title="Replaced Title")
        )
        found = await Project.find_one(Project.id == "svc-upsert-existing")
        assert found.title == "Replaced Title"

    async def test_upsert_uses_path_id_not_body_id(self, db):
        await _service(ADMIN).upsert_one({"id": "svc-path-id"}, data=_project_in("svc-body-id"))
        assert await Project.find_one(Project.id == "svc-path-id") is not None


# ---------------------------------------------------------------------------
# upsert_one — authorization (owner-or-admin), owner forcing
# ---------------------------------------------------------------------------


class TestUpsertAuthorization:
    async def test_owner_can_overwrite_own_project(self, db):
        await _insert("svc-auth-own", owner=ALICE_EMAIL)
        await _service(ALICE).upsert_one(
            {"id": "svc-auth-own"}, data=_project_in("svc-auth-own", owner=ALICE_EMAIL, title="Owner Edit")
        )
        found = await Project.find_one(Project.id == "svc-auth-own")
        assert found.title == "Owner Edit"

    async def test_admin_can_overwrite_any_project(self, db):
        await _insert("svc-auth-admin", owner=ALICE_EMAIL)
        await _service(ADMIN).upsert_one(
            {"id": "svc-auth-admin"}, data=_project_in("svc-auth-admin", owner=ALICE_EMAIL, title="Admin Edit")
        )
        found = await Project.find_one(Project.id == "svc-auth-admin")
        assert found.title == "Admin Edit"

    async def test_non_owner_cannot_overwrite(self, db):
        await _insert("svc-auth-other", owner=ALICE_EMAIL, title="Original")
        with pytest.raises(AppPermissionError):
            await _service(BOB).upsert_one(
                {"id": "svc-auth-other"}, data=_project_in("svc-auth-other", owner=ALICE_EMAIL, title="Hijacked")
            )
        found = await Project.find_one(Project.id == "svc-auth-other")
        assert found.title == "Original"

    async def test_new_project_sets_owner_to_caller(self, db):
        # Body carries a foreign owner; the authenticated caller's identity must win on insert.
        await _service(BOB).upsert_one({"id": "svc-auth-newowner"}, data=_project_in("svc-auth-newowner", owner=ALICE_EMAIL))
        found = await Project.find_one(Project.id == "svc-auth-newowner")
        assert found.owner == BOB_EMAIL

    async def test_update_preserves_original_owner(self, db):
        await _insert("svc-auth-preserve", owner=ALICE_EMAIL)
        # Alice tries to reassign ownership via the body; owner must stay hers.
        await _service(ALICE).upsert_one(
            {"id": "svc-auth-preserve"}, data=_project_in("svc-auth-preserve", owner=BOB_EMAIL, title="Edit")
        )
        found = await Project.find_one(Project.id == "svc-auth-preserve")
        assert found.owner == ALICE_EMAIL

    async def test_anonymous_cannot_upsert(self, db):
        with pytest.raises(AppPermissionError):
            await _service(User()).upsert_one({"id": "svc-anon"}, data=_project_in("svc-anon"))


# ---------------------------------------------------------------------------
# is_approved is admin-only (via PATCH)
# ---------------------------------------------------------------------------


class TestApprovalIsAdminOnly:
    async def test_non_admin_cannot_patch_is_approved(self, db):
        await _insert("svc-appr-patch", owner=ALICE_EMAIL)
        with pytest.raises(AppPermissionError):
            await _service(ALICE).update_one({"id": "svc-appr-patch"}, ProjectPatch(is_approved=True))
        found = await Project.find_one(Project.id == "svc-appr-patch")
        assert found.is_approved is False

    async def test_admin_can_patch_is_approved(self, db):
        await _insert("svc-appr-admin", owner=ALICE_EMAIL)
        await _service(ADMIN).update_one({"id": "svc-appr-admin"}, ProjectPatch(is_approved=True))
        found = await Project.find_one(Project.id == "svc-appr-admin")
        assert found.is_approved is True

    async def test_non_admin_plain_patch_is_allowed(self, db):
        await _insert("svc-patch-plain", owner=ALICE_EMAIL)
        await _service(ALICE).update_one({"id": "svc-patch-plain"}, ProjectPatch(title="New Title"))
        found = await Project.find_one(Project.id == "svc-patch-plain")
        assert found.title == "New Title"

    async def test_patch_missing_project_raises_not_found(self, db):
        with pytest.raises(NotFoundError):
            await _service(ADMIN).update_one({"id": "svc-patch-ghost"}, ProjectPatch(title="xyz"))


# ---------------------------------------------------------------------------
# a project cannot be public unless approved (enforced on PATCH and PUT)
# ---------------------------------------------------------------------------


class TestPublicRequiresApproved:
    async def test_patch_public_on_unapproved_rejected(self, db):
        await _insert("svc-pub-unappr", owner=ALICE_EMAIL, is_approved=False)
        with pytest.raises(ValidationError, match="approved"):
            await _service(ADMIN).update_one({"id": "svc-pub-unappr"}, ProjectPatch(is_public=True))
        found = await Project.find_one(Project.id == "svc-pub-unappr")
        assert found.is_public is False

    async def test_patch_public_and_approved_together_succeeds(self, db):
        await _insert("svc-pub-both", owner=ALICE_EMAIL, is_approved=False)
        await _service(ADMIN).update_one({"id": "svc-pub-both"}, ProjectPatch(is_public=True, is_approved=True))
        found = await Project.find_one(Project.id == "svc-pub-both")
        assert found.is_public is True
        assert found.is_approved is True

    async def test_patch_public_on_approved_succeeds(self, db):
        await _insert("svc-pub-approved", owner=ALICE_EMAIL, is_approved=True)
        await _service(ADMIN).update_one({"id": "svc-pub-approved"}, ProjectPatch(is_public=True))
        found = await Project.find_one(Project.id == "svc-pub-approved")
        assert found.is_public is True


# ---------------------------------------------------------------------------
# upsert (PUT) cannot set server-managed fields; it preserves them on update
# ---------------------------------------------------------------------------


class TestServerManagedFields:
    async def test_new_project_is_private_and_unapproved(self, db):
        await _service(BOB).upsert_one({"id": "svc-srv-new"}, data=_project_in("svc-srv-new"))
        found = await Project.find_one(Project.id == "svc-srv-new")
        assert found.is_public is False
        assert found.is_approved is False

    async def test_admin_plain_upsert_leaves_unapproved(self, db):
        # A plain PUT (no is_approved in the body) creates an unapproved project even for an admin.
        await _service(ADMIN).upsert_one({"id": "svc-srv-admin-new"}, data=_project_in("svc-srv-admin-new"))
        found = await Project.find_one(Project.id == "svc-srv-admin-new")
        assert found.is_approved is False

    async def test_non_admin_cannot_approve_new_project_via_upsert(self, db):
        await _service(ALICE).upsert_one(
            {"id": "svc-srv-approve-new"}, data=_project_in("svc-srv-approve-new", is_approved=True)
        )
        found = await Project.find_one(Project.id == "svc-srv-approve-new")
        assert found.is_approved is False

    async def test_non_admin_cannot_change_approval_via_upsert(self, db):
        await _insert("svc-srv-approve-existing", owner=ALICE_EMAIL, is_approved=True)
        # The owner (non-admin) overwrites and tries to un-approve; approval must stick.
        await _service(ALICE).upsert_one(
            {"id": "svc-srv-approve-existing"},
            data=_project_in("svc-srv-approve-existing", owner=ALICE_EMAIL, is_approved=False),
        )
        found = await Project.find_one(Project.id == "svc-srv-approve-existing")
        assert found.is_approved is True

    async def test_update_preserves_stats_and_columns(self, db):
        await _insert("svc-srv-preserve", owner=ALICE_EMAIL)
        stored = await Project.find_one(Project.id == "svc-srv-preserve")
        stored.stats = Stats(columns=2, contributions=5, tables=1, structures=0, attachments=0, size=42.0)
        stored.columns = [Column(path="data.band_gap", min=0.0, max=1.0, unit="eV")]
        await stored.save()
        # A full overwrite must not clobber the server-owned rollups.
        await _service(ADMIN).upsert_one({"id": "svc-srv-preserve"}, _project_in("svc-srv-preserve", title="Edited"))
        found = await Project.find_one(Project.id == "svc-srv-preserve")
        assert found.title == "Edited"
        assert found.stats.contributions == 5
        assert [c.path for c in found.columns] == ["data.band_gap"]

    async def test_new_starts_with_empty_stats(self, db):
        await _service(ALICE).upsert_one({"id": "svc-srv-new-empty"}, _project_in("svc-srv-new-empty"))
        found = await Project.find_one(Project.id == "svc-srv-new-empty")
        assert found.stats == Stats()
        assert found.columns == []


# ---------------------------------------------------------------------------
# Per-user project-count quota (max_projects)
# ---------------------------------------------------------------------------


class TestProjectCountQuota:
    async def test_upsert_new_project_over_cap_rejected(self, db, monkeypatch):
        from mpcontribs_api.config import get_settings

        monkeypatch.setattr(get_settings().consumer.project, "max_projects", 1)
        await _insert("svc-owned-1", owner=ALICE_EMAIL)
        with pytest.raises(AppPermissionError):
            await _service(ALICE).upsert_one({"id": "svc-new-proj"}, _project_in("svc-new-proj", owner=ALICE_EMAIL))

    async def test_upsert_existing_project_allowed_at_cap(self, db, monkeypatch):
        # Updating a project you already own must never be blocked by the cap. Only new ones count.
        from mpcontribs_api.config import get_settings

        monkeypatch.setattr(get_settings().consumer.project, "max_projects", 1)
        await _insert("svc-owned-only", owner=ALICE_EMAIL)
        result = await _service(ALICE).upsert_one(
            {"id": "svc-owned-only"}, _project_in("svc-owned-only", owner=ALICE_EMAIL, title="Updated Title")
        )
        assert result.title == "Updated Title"

    async def test_injected_consumer_override_lowers_cap(self, db):
        # A per-consumer override injected into the service tightens the cap to 1, without touching config.
        await _insert("svc-override-1", owner=ALICE_EMAIL)
        service = _service(ALICE, limits=ConsumerLimits(project=ConsumerProjectLimits(max_projects=1)))
        with pytest.raises(AppPermissionError):
            await service.upsert_one({"id": "svc-override-2"}, _project_in("svc-override-2", owner=ALICE_EMAIL))


# ---------------------------------------------------------------------------
# Read scope — GET "" and GET /{id} filter by user visibility
# ---------------------------------------------------------------------------


class TestReadScope:
    async def test_get_many_hides_private_unowned(self, db):
        # Alice owns one public+approved project and one private one. Bob (no roles) sees only the
        # public+approved one; Alice's private project must not leak into his listing.
        await _insert("scope-pub", owner=ALICE_EMAIL, is_public=True, is_approved=True)
        await _insert("scope-priv", owner=ALICE_EMAIL, is_public=False)
        page = await _service(BOB).read_many(filter=ProjectFilter(), pagination=CursorParams(), fields=None)
        ids = {p.id for p in page.items}
        assert "scope-pub" in ids
        assert "scope-priv" not in ids

    async def test_get_one_private_unowned_returns_none(self, db):
        await _insert("scope-one-priv", owner=ALICE_EMAIL, is_public=False)
        assert await _service(BOB).read_one({"id": "scope-one-priv"}, fields=None) is None

    async def test_get_one_public_visible_to_non_owner(self, db):
        await _insert("scope-one-pub", owner=ALICE_EMAIL, is_public=True, is_approved=True)
        found = await _service(BOB).read_one({"id": "scope-one-pub"}, fields=None)
        assert found is not None and found.id == "scope-one-pub"

    async def test_owner_sees_own_private_project(self, db):
        await _insert("scope-own-priv", owner=ALICE_EMAIL, is_public=False)
        found = await _service(ALICE).read_one({"id": "scope-own-priv"}, fields=None)
        assert found is not None and found.id == "scope-own-priv"


# ---------------------------------------------------------------------------
# Initiative assignment on create (PUT) — guarded like the PATCH path
#
# A body-supplied `initiative` (id or slug) is routed through the same resolution as PATCH: the
# target must exist and be visible, the caller must manage it, and an unapproved target must have
# room under its member cap. A body can never write a raw link straight to the document.
# ---------------------------------------------------------------------------


class TestCreateWithInitiative:
    async def test_create_assigns_by_slug(self, db):
        init = await _insert_initiative("cwi-slug", ALICE)
        created = await _service(ALICE).upsert_one(
            {"id": "cwi-proj-slug"}, _project_in("cwi-proj-slug", owner=ALICE_EMAIL, initiative="cwi-slug")
        )
        assert _assigned_id(created) == init.id

    async def test_create_assigns_by_id(self, db):
        init = await _insert_initiative("cwi-id", ALICE)
        created = await _service(ALICE).upsert_one(
            {"id": "cwi-proj-id"}, _project_in("cwi-proj-id", owner=ALICE_EMAIL, initiative=str(init.id))
        )
        assert _assigned_id(created) == init.id

    async def test_create_without_initiative_leaves_link_unset(self, db):
        created = await _service(ALICE).upsert_one({"id": "cwi-none"}, _project_in("cwi-none", owner=ALICE_EMAIL))
        assert _assigned_id(created) is None

    async def test_create_to_missing_initiative_is_not_found(self, db):
        with pytest.raises(NotFoundError):
            await _service(ALICE).upsert_one(
                {"id": "cwi-ghost"}, _project_in("cwi-ghost", owner=ALICE_EMAIL, initiative="no-such-init")
            )

    async def test_create_to_unmanaged_initiative_rejected(self, db):
        # Carol can *see* this public+approved initiative but neither owns nor collaborates on it, so
        # she cannot assign her new project to it — assignment needs manage rights, not just read.
        await _insert_initiative("cwi-unmanaged", ALICE)
        await MongoDbInitiativeRepository(ADMIN).update_one(
            {"slug": "cwi-unmanaged"}, InitiativePatch(is_approved=True, is_public=True)
        )
        with pytest.raises(AppPermissionError):
            await _service(CAROL).upsert_one(
                {"id": "cwi-carol"}, _project_in("cwi-carol", owner=CAROL_EMAIL, initiative="cwi-unmanaged")
            )
        assert await Project.find_one(Project.id == "cwi-carol") is None

    async def test_create_to_invisible_initiative_is_not_found(self, db):
        # Alice's private initiative is invisible to Carol, so it reads as not-found (not a 403).
        await _insert_initiative("cwi-invisible", ALICE)
        with pytest.raises(NotFoundError):
            await _service(CAROL).upsert_one(
                {"id": "cwi-carol-2"}, _project_in("cwi-carol-2", owner=CAROL_EMAIL, initiative="cwi-invisible")
            )

    async def test_collaborator_can_assign_on_create(self, db):
        init = await _insert_initiative("cwi-collab", ALICE)
        bob = _collaborator("cwi-collab")
        created = await _service(bob).upsert_one(
            {"id": "cwi-collab-proj"}, _project_in("cwi-collab-proj", owner=BOB_EMAIL, initiative="cwi-collab")
        )
        assert _assigned_id(created) == init.id

    async def test_create_over_member_cap_rejected(self, db, monkeypatch):
        # Isolate the initiative member cap from the per-account project-count cap.
        member_cap = get_settings().domain.initiatives.max_projects_per_unapproved
        monkeypatch.setattr(get_settings().consumer, "max_projects", member_cap + 10)
        await _insert_initiative("cwi-cap", ALICE)
        for i in range(member_cap):
            await _service(ALICE).upsert_one(
                {"id": f"cwi-cap-{i}"}, _project_in(f"cwi-cap-{i}", owner=ALICE_EMAIL, initiative="cwi-cap")
            )
        with pytest.raises(ConflictError):
            await _service(ALICE).upsert_one(
                {"id": "cwi-cap-over"}, _project_in("cwi-cap-over", owner=ALICE_EMAIL, initiative="cwi-cap")
            )

    async def test_put_preserves_existing_initiative_link(self, db):
        # The bug this closes: a full replace (PUT) that omits `initiative` must NOT silently clear
        # the stored assignment. Reassignment/clearing stays on the guarded PATCH path.
        await _insert("ppi-proj", owner=ALICE_EMAIL)
        init = await _insert_initiative("ppi-init", ALICE)
        await _service(ALICE).update_one({"id": "ppi-proj"}, ProjectPatch(initiative="ppi-init"))
        await _service(ALICE).upsert_one(
            {"id": "ppi-proj"}, _project_in("ppi-proj", owner=ALICE_EMAIL, title="Replaced")
        )
        reloaded = await MongoDbProjectRepository(ADMIN).find_by_id_unscoped("ppi-proj")
        assert reloaded is not None
        assert reloaded.title == "Replaced"
        assert _assigned_id(reloaded) == init.id
