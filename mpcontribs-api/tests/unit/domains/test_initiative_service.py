"""Mock-repo unit tests for :class:`InitiativeService` write policy.

Fast and hermetic: the repository is an ``AsyncMock``, so these exercise the service's branch logic
directly — which exception each policy violation raises, and which repository primitive the happy
path calls. Real-DB behaviour is covered in ``tests/integration/db/test_initiatives_service.py``.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from beanie import PydanticObjectId

from mpcontribs_api.authz import User
from mpcontribs_api.config import get_settings
from mpcontribs_api.domains._shared.models import DeleteResponse
from mpcontribs_api.domains.initiatives.models import InitiativeIn, InitiativePatch
from mpcontribs_api.domains.initiatives.service import InitiativeService
from mpcontribs_api.exceptions import ConflictError, NotFoundError, ValidationError
from mpcontribs_api.exceptions import PermissionError as AppPermissionError

pytestmark = pytest.mark.asyncio

ADMIN = User(username="google:admin@example.com", groups=frozenset({"admin"}))
ALICE = User(username="google:alice@example.com", groups=frozenset())
ANON = User()

ALICE_EMAIL = "google:alice@example.com"


def _collaborator(slug: str, username: str = "google:bob@example.com") -> User:
    return User(username=username, groups=frozenset({f"initiative:{slug}"}))


def _existing(owner: str = ALICE_EMAIL, *, is_public: bool = False, is_approved: bool = False):
    """A stand-in for the scoped InitiativeOut a read returns (only the fields the service reads)."""
    return SimpleNamespace(
        id=PydanticObjectId(), slug="init-1", owner=owner, is_public=is_public, is_approved=is_approved
    )


def _service(user: User, *, existing=None, unapproved: int = 0):
    initiatives = AsyncMock()
    initiatives.get_one.return_value = existing
    initiatives.count_unapproved_for_owner.return_value = unapproved
    initiatives.insert_one.side_effect = lambda data, owner: SimpleNamespace(slug=data.slug, owner=owner)
    initiatives.patch_one.return_value = _existing()
    initiatives.delete_one.return_value = DeleteResponse(num_deleted=1)
    projects = AsyncMock()
    projects.clear_initiative_refs.return_value = 0
    return InitiativeService(user=user, initiatives=initiatives, projects=projects), initiatives


def _limit() -> int:
    return get_settings().domain.initiatives.max_unapproved_per_owner


# ---------------------------------------------------------------------------
# insert_one
# ---------------------------------------------------------------------------


class TestInsert:
    async def test_anonymous_raises_permission(self):
        svc, initiatives = _service(ANON)
        with pytest.raises(AppPermissionError):
            await svc.insert_one(InitiativeIn(slug="x-init", name="X"))
        initiatives.insert_one.assert_not_called()

    async def test_over_quota_raises_conflict(self):
        svc, initiatives = _service(ALICE, unapproved=_limit())
        with pytest.raises(ConflictError):
            await svc.insert_one(InitiativeIn(slug="x-init", name="X"))
        initiatives.insert_one.assert_not_called()

    async def test_admin_bypasses_quota(self):
        svc, initiatives = _service(ADMIN, unapproved=_limit() + 5)
        await svc.insert_one(InitiativeIn(slug="x-init", name="X"))
        initiatives.insert_one.assert_awaited_once()
        # count is never consulted for an admin
        initiatives.count_unapproved_for_owner.assert_not_called()

    async def test_happy_path_forces_owner(self):
        svc, initiatives = _service(ALICE, unapproved=0)
        await svc.insert_one(InitiativeIn(slug="x-init", name="X"))
        assert initiatives.insert_one.call_args.kwargs["owner"] == ALICE_EMAIL


# ---------------------------------------------------------------------------
# patch_one
# ---------------------------------------------------------------------------


class TestPatch:
    async def test_missing_raises_not_found(self):
        svc, initiatives = _service(ADMIN, existing=None)
        with pytest.raises(NotFoundError):
            await svc.patch_one({"slug": "init-1"}, InitiativePatch(name="new-name"))
        initiatives.patch_one.assert_not_called()

    async def test_unmanaged_caller_raises_permission(self):
        # A stranger who can see the initiative still cannot manage it.
        stranger = User(username="google:carol@example.com", groups=frozenset())
        svc, initiatives = _service(stranger, existing=_existing(owner=ALICE_EMAIL))
        with pytest.raises(AppPermissionError):
            await svc.patch_one({"slug": "init-1"}, InitiativePatch(name="hijack"))
        initiatives.patch_one.assert_not_called()

    async def test_collaborator_can_patch(self):
        svc, initiatives = _service(_collaborator("init-1"), existing=_existing(owner=ALICE_EMAIL))
        await svc.patch_one({"slug": "init-1"}, InitiativePatch(name="ok"))
        initiatives.patch_one.assert_awaited_once()

    async def test_non_admin_approve_raises_permission(self):
        svc, initiatives = _service(ALICE, existing=_existing(owner=ALICE_EMAIL))
        with pytest.raises(AppPermissionError):
            await svc.patch_one({"slug": "init-1"}, InitiativePatch(is_approved=True))
        initiatives.patch_one.assert_not_called()

    async def test_public_on_unapproved_raises_validation(self):
        svc, initiatives = _service(ADMIN, existing=_existing(owner=ALICE_EMAIL, is_approved=False))
        with pytest.raises(ValidationError):
            await svc.patch_one({"slug": "init-1"}, InitiativePatch(is_public=True))
        initiatives.patch_one.assert_not_called()

    async def test_admin_approve_and_publish_together_ok(self):
        svc, initiatives = _service(ADMIN, existing=_existing(owner=ALICE_EMAIL, is_approved=False))
        await svc.patch_one({"slug": "init-1"}, InitiativePatch(is_approved=True, is_public=True))
        initiatives.patch_one.assert_awaited_once()


# ---------------------------------------------------------------------------
# delete_one
# ---------------------------------------------------------------------------


class TestDelete:
    async def test_missing_raises_not_found(self):
        svc, initiatives = _service(ALICE, existing=None)
        with pytest.raises(NotFoundError):
            await svc.delete_one({"slug": "init-1"})
        initiatives.delete_one.assert_not_called()

    async def test_collaborator_cannot_delete(self):
        # Collaborators may manage/patch but not dissolve — delete needs owner or admin.
        svc, initiatives = _service(_collaborator("init-1"), existing=_existing(owner=ALICE_EMAIL))
        with pytest.raises(AppPermissionError):
            await svc.delete_one({"slug": "init-1"})
        initiatives.delete_one.assert_not_called()

    async def test_owner_deletes(self):
        existing = _existing(owner=ALICE_EMAIL)
        svc, initiatives = _service(ALICE, existing=existing)
        await svc.delete_one({"slug": "init-1"})
        initiatives.delete_one.assert_awaited_once_with({"slug": "init-1"})
        # The member projects' dangling links are cleared by the deleted initiative's id.
        svc._projects.clear_initiative_refs.assert_awaited_once_with(existing.id)

    async def test_admin_deletes_any(self):
        svc, initiatives = _service(ADMIN, existing=_existing(owner=ALICE_EMAIL))
        await svc.delete_one({"slug": "init-1"})
        initiatives.delete_one.assert_awaited_once()

    async def test_denied_delete_leaves_projects_untouched(self):
        # A blocked delete must not orphan project links: no cleanup runs when the gate rejects.
        svc, initiatives = _service(_collaborator("init-1"), existing=_existing(owner=ALICE_EMAIL))
        with pytest.raises(AppPermissionError):
            await svc.delete_one({"slug": "init-1"})
        svc._projects.clear_initiative_refs.assert_not_called()
