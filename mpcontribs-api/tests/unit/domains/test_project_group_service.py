from unittest.mock import AsyncMock, MagicMock

import pytest
from beanie import Link, PydanticObjectId
from bson import DBRef

from mpcontribs_api.authz import User
from mpcontribs_api.domains.project_groups.models import ProjectGroupIn, ProjectGroupOut
from mpcontribs_api.domains.project_groups.service import ProjectGroupService
from mpcontribs_api.domains.projects.models import Project
from mpcontribs_api.exceptions import ConflictError, NotFoundError

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_service(group: ProjectGroupOut | None, *, visible_projects: set[str] | None = None, ambiguous: bool = False):
    """Build a service over stubbed repos.

    ``group`` is what the groups repo resolves to (None => not found). ``visible_projects`` gates
    which project ids the projects repo reports as existing/visible. ``ambiguous`` makes identifier
    resolution raise ConflictError (duplicate under the unique key).
    """
    visible = visible_projects or set()
    groups = AsyncMock()
    projects = AsyncMock()
    # insert_one forces owner to the caller for non-admins; construct the service as an admin so these
    # payload-identity assertions exercise the pass-through path (owner-forcing is covered end-to-end
    # in the db service test).
    admin = User(username="google:admin@example.com", groups=frozenset({"admin"}))

    if ambiguous:
        groups.get_one.side_effect = ConflictError("ambiguous")
    else:
        groups.get_one.return_value = group
    # coerce_identifiers is a sync repo method; keep it sync so the service gets a real dict, not a coroutine.
    def _coerce_identifiers(identifiers):
        if isinstance(identifiers.get("id"), str):
            return {**identifiers, "id": PydanticObjectId(identifiers["id"])}
        return identifiers

    groups.coerce_identifiers = MagicMock(side_effect=_coerce_identifiers)
    groups.add_project_refs.return_value = group
    groups.delete_project_refs.return_value = group

    async def _get_project(identifiers, fields=None):
        pid = identifiers["id"]
        return {"_id": pid} if pid in visible else None

    projects.get_one.side_effect = _get_project

    return ProjectGroupService(user=admin, groups=groups, projects=projects), groups, projects


def _group(project_ids: list[str] | None = None) -> ProjectGroupOut:
    group = ProjectGroupOut.model_validate(
        {"_id": PydanticObjectId(), "name": "g", "owner": "google:a@b.com", "projects": []}
    )
    # Members are stored as Links (DBRefs); set them directly to sidestep Link revalidation.
    group.projects = [Link(DBRef("projects", pid), Project) for pid in (project_ids or [])]
    return group


# ---------------------------------------------------------------------------
#.insert_one
# ---------------------------------------------------------------------------


class TestInsert_one:
    def _payload(self, projects: list[str]) -> ProjectGroupIn:
        return ProjectGroupIn(name="g", owner="google:a@b.com", description="d", projects=projects)

    async def test_all_projects_valid_insert_ones(self):
        service, groups, _ = _make_service(None, visible_projects={"mp-1", "mp-2"})
        groups.insert_one.return_value = "stored"
        payload = self._payload(["mp-1", "mp-2"])
        result = await service.insert_one(payload)
        assert result == "stored"
        groups.insert_one.assert_awaited_once_with(in_resource=payload)

    async def test_missing_project_raises_not_found_and_skips_insert_one(self):
        service, groups, _ = _make_service(None, visible_projects={"mp-1"})
        with pytest.raises(NotFoundError) as exc:
            await service.insert_one(self._payload(["mp-1", "ghost"]))
        assert exc.value.context["ids"] == ["ghost"]
        groups.insert_one.assert_not_awaited()

    async def test_empty_projects_insert_ones_without_validation(self):
        service, groups, projects = _make_service(None)
        payload = self._payload([])
        await service.insert_one(payload)
        projects.get_one.assert_not_awaited()
        groups.insert_one.assert_awaited_once_with(in_resource=payload)


# ---------------------------------------------------------------------------
# Group resolution
# ---------------------------------------------------------------------------


class TestGroupResolution:
    async def test_add_by_id_missing_group_raises_not_found(self):
        service, _, _ = _make_service(None)
        with pytest.raises(NotFoundError):
            await service.add_projects({"id": "0" * 24}, ["mp-1"])

    async def test_add_by_identifiers_missing_group_raises_not_found(self):
        service, _, _ = _make_service(None)
        with pytest.raises(NotFoundError):
            await service.add_projects({"name": "g", "owner": "google:a@b.com"}, ["mp-1"])

    async def test_ambiguous_identifiers_propagate_conflict(self):
        service, _, _ = _make_service(_group(), ambiguous=True)
        with pytest.raises(ConflictError):
            await service.add_projects({"name": "g", "owner": "google:a@b.com"}, ["mp-1"])


# ---------------------------------------------------------------------------
# add
# ---------------------------------------------------------------------------


class TestAddProjects:
    async def test_valid_projects_are_added(self):
        group = _group()
        service, groups, _ = _make_service(group, visible_projects={"mp-1", "mp-2"})
        summary = await service.add_projects({"id": str(group.id)}, ["mp-1", "mp-2"])
        assert summary.total == 2
        assert summary.succeeded == ["mp-1", "mp-2"]
        assert summary.failed == []
        groups.add_project_refs.assert_awaited_once_with(group.id, ["mp-1", "mp-2"])

    async def test_missing_project_reported_as_failure(self):
        group = _group()
        service, groups, _ = _make_service(group, visible_projects={"mp-1"})
        summary = await service.add_projects({"id": str(group.id)}, ["mp-1", "ghost"])
        assert summary.succeeded == ["mp-1"]
        assert len(summary.failed) == 1
        assert summary.failed[0].index == 1
        assert summary.failed[0].error_code == "not_found"
        # only the valid id is written
        groups.add_project_refs.assert_awaited_once_with(group.id, ["mp-1"])

    async def test_no_valid_projects_skips_update(self):
        group = _group()
        service, groups, _ = _make_service(group, visible_projects=set())
        summary = await service.add_projects({"id": str(group.id)}, ["ghost"])
        assert summary.succeeded == []
        assert len(summary.failed) == 1
        groups.add_project_refs.assert_not_awaited()

    async def test_duplicate_input_added_once(self):
        group = _group()
        service, groups, _ = _make_service(group, visible_projects={"mp-1"})
        summary = await service.add_projects({"id": str(group.id)}, ["mp-1", "mp-1"])
        assert summary.succeeded == ["mp-1"]
        groups.add_project_refs.assert_awaited_once_with(group.id, ["mp-1"])


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


class TestDeleteProjects:
    async def test_members_deleted_non_members_reported(self):
        group = _group(["mp-1", "mp-2"])
        service, groups, _ = _make_service(group)
        summary = await service.delete_projects({"id": str(group.id)}, ["mp-1", "ghost"])
        assert summary.succeeded == ["mp-1"]
        assert len(summary.failed) == 1
        assert summary.failed[0].index == 1
        assert summary.failed[0].error_code == "not_found"
        groups.delete_project_refs.assert_awaited_once_with(group.id, ["mp-1"])

    async def test_no_members_skips_update(self):
        group = _group(["mp-1"])
        service, groups, _ = _make_service(group)
        summary = await service.delete_projects({"id": str(group.id)}, ["ghost"])
        assert summary.succeeded == []
        assert len(summary.failed) == 1
        groups.delete_project_refs.assert_not_awaited()
