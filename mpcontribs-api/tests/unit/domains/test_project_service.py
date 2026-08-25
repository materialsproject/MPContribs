from unittest.mock import AsyncMock, MagicMock

import pytest
from beanie import PydanticObjectId
from bson import DBRef

from mpcontribs_api.authz import User
from mpcontribs_api.domains._shared.models import DeleteResponse
from mpcontribs_api.domains.consumers.models import ConsumerSettings
from mpcontribs_api.domains.projects.models import Column, Project, ProjectIn, ProjectPatch, Stats
from mpcontribs_api.domains.projects.service import ProjectService
from mpcontribs_api.exceptions import NotFoundError, ValidationError
from mpcontribs_api.exceptions import PermissionError as AppPermissionError

pytestmark = pytest.mark.asyncio

ADMIN = User(username="google:admin@example.com", groups=frozenset({"admin"}))
ALICE = User(username="google:alice@example.com", groups=frozenset())
BOB = User(username="google:bob@example.com", groups=frozenset())
ANON = User()

ALICE_EMAIL = "google:alice@example.com"
BOB_EMAIL = "google:bob@example.com"


def _project(
    id: str = "proj-1",
    owner: str = ALICE_EMAIL,
    *,
    is_public: bool = False,
    is_approved: bool = False,
    stats: Stats | None = None,
    columns: list[Column] | None = None,
) -> Project:
    doc = Project.from_input_model(
        ProjectIn(
            title="test-project",
            authors="a",
            description="d",
            owner=owner,
            is_public=is_public,
            is_approved=is_approved,
        ),
        id=id,
    )
    if stats is not None:
        doc.stats = stats
    if columns is not None:
        doc.columns = columns
    return doc


def _project_in(id: str = "p1", **overrides) -> ProjectIn:
    defaults = {"title": "test-project", "authors": "a", "description": "d", "owner": ALICE_EMAIL}
    defaults.update(overrides)
    return ProjectIn(**defaults)


def _service(user: User, *, existing=None, scoped=None, count: int = 0, limits: ConsumerSettings | None = None):
    projects = AsyncMock()
    # The service builds documents via ``repo.document_model.from_input_model`` — keep that the real
    # class (an AsyncMock child would turn the classmethod call into a coroutine).
    projects.document_model = Project
    projects.find_by_id_unscoped.return_value = existing
    projects.read_one.return_value = scoped
    projects.count_matching.return_value = count
    projects.upsert_one.side_effect = lambda doc, **kw: doc
    projects.update_one.return_value = _project()
    projects.delete_one.return_value = DeleteResponse(num_deleted=1)
    initiatives = AsyncMock()
    svc = ProjectService(user=user, projects=projects, initiatives=initiatives, limits=limits)
    return svc, projects, initiatives


# ---------------------------------------------------------------------------
# delete_one
# ---------------------------------------------------------------------------


class TestDelete:
    async def test_missing_raises_not_found(self):
        svc, projects, _ = _service(ALICE, scoped=None)
        with pytest.raises(NotFoundError):
            await svc.delete_one({"id": "proj-1"})
        projects.delete_one.assert_not_called()

    async def test_non_owner_raises_permission(self):
        svc, projects, _ = _service(BOB, scoped=_project(owner=ALICE_EMAIL))
        with pytest.raises(AppPermissionError):
            await svc.delete_one({"id": "proj-1"})
        projects.delete_one.assert_not_called()

    async def test_owner_deletes(self):
        svc, projects, _ = _service(ALICE, scoped=_project(owner=ALICE_EMAIL))
        await svc.delete_one({"id": "proj-1"})
        projects.delete_one.assert_awaited_once_with({"id": "proj-1"})

    async def test_admin_deletes_any(self):
        svc, projects, _ = _service(ADMIN, scoped=_project(owner=ALICE_EMAIL))
        await svc.delete_one({"id": "proj-1"})
        projects.delete_one.assert_awaited_once()


# ---------------------------------------------------------------------------
# upsert_one
# ---------------------------------------------------------------------------


class TestUpsert:
    async def test_anonymous_raises_permission(self):
        svc, projects, _ = _service(ANON)
        with pytest.raises(AppPermissionError):
            await svc.upsert_one({"id": "proj-1"}, _project_in("p1"))
        projects.upsert_one.assert_not_called()

    async def test_existing_non_owner_raises_permission(self):
        svc, projects, _ = _service(BOB, existing=_project(owner=ALICE_EMAIL))
        with pytest.raises(AppPermissionError):
            await svc.upsert_one({"id": "proj-1"}, _project_in("p1"))
        projects.upsert_one.assert_not_called()

    async def test_update_preserves_owner_and_server_fields(self):
        existing = _project(
            owner=ALICE_EMAIL,
            is_public=True,
            is_approved=True,
            stats=Stats(contributions=9),
            columns=[Column(path="data.x")],
        )
        svc, projects, _ = _service(ALICE, existing=existing)
        # Body tries to reassign owner and drop publication; both must be ignored/preserved.
        await svc.upsert_one({"id": "proj-1"}, _project_in("p1", owner=BOB_EMAIL, is_public=False))
        saved = projects.upsert_one.call_args.args[0]
        assert saved.owner == ALICE_EMAIL
        assert saved.is_public is True
        assert saved.is_approved is True
        assert saved.stats.contributions == 9
        assert [c.path for c in saved.columns] == ["data.x"]

    async def test_new_forces_owner_and_unapproves(self):
        svc, projects, _ = _service(BOB, existing=None, count=0)
        await svc.upsert_one({"id": "proj-1"}, _project_in("p1", owner=ALICE_EMAIL, is_approved=True))
        saved = projects.upsert_one.call_args.args[0]
        assert saved.owner == BOB_EMAIL
        assert saved.is_approved is False

    async def test_new_over_cap_raises_permission(self):
        svc, projects, _ = _service(ALICE, existing=None, count=5, limits=ConsumerSettings(max_projects=2))
        with pytest.raises(AppPermissionError):
            await svc.upsert_one({"id": "proj-1"}, _project_in("p1", owner=ALICE_EMAIL))
        projects.upsert_one.assert_not_called()

    async def test_public_unapproved_raises_validation(self):
        # Admin new project: approval is not forced off, so a public+unapproved body trips the invariant.
        svc, projects, _ = _service(ADMIN, existing=None, count=0)
        with pytest.raises(ValidationError):
            await svc.upsert_one({"id": "proj-1"}, _project_in("p1", is_public=True, is_approved=False))
        projects.upsert_one.assert_not_called()


# ---------------------------------------------------------------------------
# update_one
# ---------------------------------------------------------------------------


class TestPatch:
    async def test_non_admin_is_approved_raises_permission(self):
        svc, projects, _ = _service(ALICE, scoped=_project())
        with pytest.raises(AppPermissionError):
            await svc.update_one({"id": "proj-1"}, ProjectPatch(is_approved=True))
        projects.update_one.assert_not_called()

    async def test_missing_raises_not_found(self):
        svc, projects, _ = _service(ADMIN, scoped=None)
        with pytest.raises(NotFoundError):
            await svc.update_one({"id": "proj-1"}, ProjectPatch(title="new-title"))
        projects.update_one.assert_not_called()

    async def test_public_on_unapproved_raises_validation(self):
        svc, projects, _ = _service(ADMIN, scoped=_project(is_approved=False, is_public=False))
        with pytest.raises(ValidationError):
            await svc.update_one({"id": "proj-1"}, ProjectPatch(is_public=True))
        projects.update_one.assert_not_called()

    async def test_plain_patch_forwards_to_repo(self):
        svc, projects, _ = _service(ADMIN, scoped=_project(is_approved=True))
        await svc.update_one({"id": "proj-1"}, ProjectPatch(title="new"))
        projects.update_one.assert_awaited_once()
        # plain path: no extra_set
        assert "extra_set" not in projects.update_one.call_args.kwargs

    async def test_initiative_assignment_resolves_link_and_sets_extra(self):
        oid = PydanticObjectId()
        svc, projects, initiatives = _service(ADMIN, scoped=_project(is_approved=True))
        initiatives.read_one.return_value = MagicMock(id=oid, owner="someone@x.com", is_approved=True)
        await svc.update_one({"id": "proj-1"}, ProjectPatch(initiative="solar"))
        # The service resolves the slug to a DBRef and hands it to the repo via extra_set.
        extra = projects.update_one.call_args.kwargs["extra_set"]
        assert extra["initiative"] == DBRef("initiatives", oid)

    async def test_initiative_unassign_passes_none(self):
        svc, projects, initiatives = _service(ADMIN, scoped=_project(is_approved=True))
        await svc.update_one({"id": "proj-1"}, ProjectPatch(initiative=None))
        initiatives.read_one.assert_not_called()
        assert projects.update_one.call_args.kwargs["extra_set"] == {"initiative": None}
