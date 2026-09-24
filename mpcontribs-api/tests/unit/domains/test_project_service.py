from unittest.mock import AsyncMock, MagicMock

import pytest
from beanie import PydanticObjectId
from bson import DBRef

from mpcontribs_api.authz import User
from mpcontribs_api.config import ConsumerLimits, ConsumerProjectLimits
from mpcontribs_api.domains._shared.models import DeleteResponse
from mpcontribs_api.domains._shared.types import DownloadFormat
from mpcontribs_api.domains.contributions.models import ContributionFilter
from mpcontribs_api.domains.projects.models import (
    Column,
    Project,
    ProjectDownloadRequest,
    ProjectFilter,
    ProjectIn,
    ProjectPatch,
    Stats,
)
from mpcontribs_api.domains.projects.service import ProjectService
from mpcontribs_api.domains.structures.models import StructureFilter
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
            authors="abc",
            description="abc",
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
    defaults = {"title": "test-project", "authors": "abc", "description": "abc", "owner": ALICE_EMAIL}
    defaults.update(overrides)
    return ProjectIn(**defaults)


def _service(user: User, *, existing=None, scoped=None, count: int = 0, limits: ConsumerLimits | None = None):
    projects = AsyncMock()
    # The service builds documents via ``repo.document_model.from_input_model`` — keep that the real
    # class (an AsyncMock child would turn the classmethod call into a coroutine).
    projects.document_model = Project
    projects.find_by_id_unscoped.return_value = existing
    projects.read_one.return_value = scoped
    projects.count_matching.return_value = count
    # PUT does a full-replace-by-id (repo.replace_one(id, doc)); return the doc it was handed.
    projects.replace_one.side_effect = lambda id, doc, **kw: doc
    projects.update_one.return_value = _project()
    projects.delete_one.return_value = DeleteResponse(num_deleted=1)
    initiatives = AsyncMock()
    svc = ProjectService(
        user=user,
        projects=projects,
        initiatives=initiatives,
        contributions=AsyncMock(),
        structures=AsyncMock(),
        tables=AsyncMock(),
        attachments=AsyncMock(),
        downloads=AsyncMock(),
        limits=limits,
    )
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
        projects.replace_one.assert_not_called()

    async def test_existing_non_owner_raises_permission(self):
        svc, projects, _ = _service(BOB, existing=_project(owner=ALICE_EMAIL))
        with pytest.raises(AppPermissionError):
            await svc.upsert_one({"id": "proj-1"}, _project_in("p1"))
        projects.replace_one.assert_not_called()

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
        saved = projects.replace_one.call_args.args[1]
        assert saved.owner == ALICE_EMAIL
        assert saved.is_public is True
        assert saved.is_approved is True
        assert saved.stats.contributions == 9
        assert [c.path for c in saved.columns] == ["data.x"]

    async def test_new_forces_owner_and_unapproves(self):
        svc, projects, _ = _service(BOB, existing=None, count=0)
        await svc.upsert_one({"id": "proj-1"}, _project_in("p1", owner=ALICE_EMAIL, is_approved=True))
        saved = projects.replace_one.call_args.args[1]
        assert saved.owner == BOB_EMAIL
        assert saved.is_approved is False

    async def test_new_over_cap_raises_permission(self):
        svc, projects, _ = _service(
            ALICE, existing=None, count=5, limits=ConsumerLimits(project=ConsumerProjectLimits(max_projects=2))
        )
        with pytest.raises(AppPermissionError):
            await svc.upsert_one({"id": "proj-1"}, _project_in("p1", owner=ALICE_EMAIL))
        projects.replace_one.assert_not_called()

    async def test_public_unapproved_raises_validation(self):
        # Admin new project: approval is not forced off, so a public+unapproved body trips the invariant.
        svc, projects, _ = _service(ADMIN, existing=None, count=0)
        with pytest.raises(ValidationError):
            await svc.upsert_one({"id": "proj-1"}, _project_in("p1", is_public=True, is_approved=False))
        projects.replace_one.assert_not_called()


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


# ---------------------------------------------------------------------------
# queue_download: builds the {collection: [scoped_query]} bundle map
# ---------------------------------------------------------------------------


def _download_service():
    """A ProjectService whose repos stub ``build_download_query`` with per-collection sentinels."""
    projects = AsyncMock()
    projects.build_download_query = MagicMock(return_value={"proj": True})
    contributions = AsyncMock()
    contributions.build_download_query = MagicMock(return_value={"contrib": True})
    structures = AsyncMock()
    structures.build_download_query = MagicMock(return_value={"struct": True})
    tables = AsyncMock()
    tables.build_download_query = MagicMock(return_value={"table": True})
    attachments = AsyncMock()
    attachments.build_download_query = MagicMock(return_value={"attach": True})
    downloads = AsyncMock()
    svc = ProjectService(
        user=User(username="alice@example.com"),
        projects=projects,
        initiatives=AsyncMock(),
        contributions=contributions,
        structures=structures,
        tables=tables,
        attachments=attachments,
        downloads=downloads,
    )
    return svc, projects, contributions, structures, downloads


class TestQueueDownload:
    """queue_download builds the {collection: [scoped_query]} map from the request body."""

    async def test_projects_only_bundle(self):
        svc, projects, contributions, _structures, downloads = _download_service()
        request = ProjectDownloadRequest(projects=ProjectFilter(is_public=True), format=DownloadFormat.CSV)

        await svc.queue_download(request)

        projects.build_download_query.assert_called_once_with(request.projects)
        contributions.build_download_query.assert_not_called()
        call = downloads.queue_download.await_args.kwargs
        assert call["query"] == {"projects": [{"proj": True}]}
        assert "domain" not in call  # the domain field was removed; collections live in query keys
        assert call["fmt"] == DownloadFormat.CSV

    async def test_bundles_contributions_when_filter_present(self):
        svc, _projects, contributions, _structures, downloads = _download_service()
        request = ProjectDownloadRequest(contributions=ContributionFilter(is_public=True))

        await svc.queue_download(request)

        contributions.build_download_query.assert_called_once_with(request.contributions)
        query = downloads.queue_download.await_args.kwargs["query"]
        assert query == {"projects": [{"proj": True}], "contributions": [{"contrib": True}]}

    async def test_component_without_contributions_injects_scoped_contributions(self):
        # A component level needs contributions as its scoped join parent; when the request omits a
        # contributions filter, a scope-only ContributionFilter is injected so nothing leaks.
        svc, _projects, contributions, structures, downloads = _download_service()
        request = ProjectDownloadRequest(structures=StructureFilter(name="POSCAR"))

        await svc.queue_download(request)

        contributions.build_download_query.assert_called_once()
        injected = contributions.build_download_query.call_args.args[0]
        assert isinstance(injected, ContributionFilter)
        structures.build_download_query.assert_called_once_with(request.structures)
        query = downloads.queue_download.await_args.kwargs["query"]
        assert query == {
            "projects": [{"proj": True}],
            "contributions": [{"contrib": True}],
            "structures": [{"struct": True}],
        }

    async def test_omitted_collections_are_absent_from_the_map(self):
        svc, _projects, _contributions, _structures, downloads = _download_service()
        request = ProjectDownloadRequest(contributions=ContributionFilter())

        await svc.queue_download(request)

        query = downloads.queue_download.await_args.kwargs["query"]
        # No component filters were given, so no component keys appear.
        assert set(query) == {"projects", "contributions"}
