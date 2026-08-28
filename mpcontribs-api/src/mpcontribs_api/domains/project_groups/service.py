from typing import Any

from beanie import Link

from mpcontribs_api.authz import ROOT_PATH, User
from mpcontribs_api.domains._shared.bulk import BulkFailure, BulkWriteSummary
from mpcontribs_api.domains._shared.models import DeleteResponse
from mpcontribs_api.domains._shared.types import ShortStr
from mpcontribs_api.domains.project_groups.models import (
    ProjectGroup,
    ProjectGroupFilter,
    ProjectGroupIn,
    ProjectGroupOut,
    ProjectGroupPatch,
)
from mpcontribs_api.domains.project_groups.repository import MongoDbProjectGroupRepository
from mpcontribs_api.domains.projects.repository import MongoDbProjectRepository
from mpcontribs_api.exceptions import NotFoundError, PermissionError
from mpcontribs_api.pagination import CursorParams, Page

# Fields the membership operations need off a resolved group: its id (target of the update), its
# owner (to authorize the mutation), and its current members (so deletion can tell members from
# non-members).
_GROUP_FIELDS = frozenset({"id", "owner", "projects"})


class ProjectGroupService:
    """Owns project-group write policy.

    Authorization lives here, not in the repository:

    - **Owner forcing** on create — a non-admin's new group is owned by the caller (admins may set an
      owner explicitly).
    - **Owner-or-admin delete** — a non-admin may delete only their own group, even one they can see;
      a caller who cannot see the group gets a 404, one who can see but does not own it gets a 403.
    - **Owner-scoped bulk delete** — a non-admin's ``delete_many`` is restricted to their own groups,
      overriding any ``owner`` in the filter, so it can never remove others' public groups.

    Membership changes validate each project against the projects collection before writing.
    """

    def __init__(
        self,
        user: User,
        groups: MongoDbProjectGroupRepository,
        projects: MongoDbProjectRepository,
    ) -> None:
        self._user = user
        self._groups = groups
        self._projects = projects

    async def insert_one(self, project_group: ProjectGroupIn) -> ProjectGroup:
        """Insert a new group after verifying every referenced project exists and is visible.

        Non-admins are set as owner automatically, while admins can specify owners.
        """
        if not self._user.is_admin(*ROOT_PATH):
            project_group = project_group.model_copy(update={"owner": self._user.username})
        existing = await self._projects.existing_ids(list(project_group.projects), scoped=True)
        missing = [pid for pid in project_group.projects if pid not in existing]
        if missing:
            raise NotFoundError("One or more projects not found or not visible", ids=missing)
        document = self._groups.document_model.from_input_model(project_group)
        return await self._groups.insert_one(document)

    async def read_many(
        self, filter: ProjectGroupFilter, pagination: CursorParams, fields: frozenset[str] | None
    ) -> Page[ProjectGroupOut]:
        """Return a page of scoped project groups matching ``filter``."""
        return await self._groups.read_many(pagination=pagination, filter=filter, fields=fields)

    async def read_one(self, identifiers: dict[str, Any], fields: frozenset[str] | None) -> ProjectGroupOut | None:
        """Return the single group matching ``identifiers`` (``{"name", "owner"}`` or ``{"id"}``)."""
        return await self._groups.read_one(identifiers, fields)

    async def delete_many(self, filter: ProjectGroupFilter) -> DeleteResponse:
        """Bulk-delete scoped project groups matching ``filter``, restricted to the caller's own.

        A non-admin's bulk delete is scoped to their own groups (overriding any ``owner`` in the
        filter) so it can never remove public groups belonging to others.
        """
        if not self._user.is_admin(*ROOT_PATH):
            filter.owner = self._user.username
        return await self._groups.delete_many(filter=filter)

    async def update_one(self, identifiers: dict[str, Any], update: ProjectGroupPatch) -> ProjectGroup:
        """Patch the single group matching ``identifiers`` (``{"name", "owner"}`` or ``{"id"}``)."""
        group = await self._groups.read_one(identifiers, fields=frozenset({"id", "owner"}))
        if group is None:
            raise NotFoundError("ProjectGroup not found", **identifiers)
        if not (self._user.is_admin(*ROOT_PATH) or group.owner == self._user.username):
            raise PermissionError(required_role="owner-or-admin")
        return await self._groups.update_one(identifiers, update)

    async def delete_one(self, identifiers: dict[str, Any]) -> DeleteResponse:
        """Delete the single group matching ``identifiers`` (``{"name", "owner"}`` or ``{"id"}``).

        Restricted to the owner or an admin. Absence (in scope) takes precedence over the ownership
        gate: a caller who cannot see the group gets a 404, one who can see it (e.g. a public group)
        but does not own it gets a 403 rather than a silent no-op.
        """
        group = await self._groups.read_one(identifiers, fields=frozenset({"id", "owner"}))
        if group is None:
            raise NotFoundError("ProjectGroup not found", **identifiers)
        if not (self._user.is_admin(*ROOT_PATH) or group.owner == self._user.username):
            raise PermissionError(required_role="owner-or-admin")
        return await self._groups.delete_one(identifiers)

    async def _resolve_one(self, identifiers: dict[str, Any]) -> ProjectGroupOut:
        """Resolve a group the caller may *mutate* matching ``identifiers``, or raise.

        ``identifiers`` is either the primary-key form ``{"id": <ObjectId str>}`` or the semantic
        ``{"name": ..., "owner": ...}``. Propagates ``ConflictError`` from the repository if
        ``(name, owner)`` identifiers are ambiguous.
        """
        group = await self._groups.read_one(identifiers, fields=_GROUP_FIELDS)
        if group is None:
            raise NotFoundError("ProjectGroup not found", **identifiers)
        if not (self._user.is_admin(*ROOT_PATH) or group.owner == self._user.username):
            raise PermissionError(required_role="owner-or-admin")
        return group  # pyright: ignore[reportReturnType]  # projected reads return the out model

    async def _add(self, group: ProjectGroupOut, project_ids: list[ShortStr]) -> BulkWriteSummary[str]:
        """Validate each project against the projects collection, then add the valid ones.

        A project that does not exist or is not visible to the caller is reported as a failed item;
        the rest are added in a single atomic ``$addToSet`` (idempotent for existing members).
        """
        existing = await self._projects.existing_ids(project_ids, scoped=True)
        failed: list[BulkFailure] = []
        valid: list[ShortStr] = []
        for index, pid in enumerate(project_ids):
            if pid not in existing:
                failed.append(
                    BulkFailure(
                        index=index,
                        identifier={"id": pid},
                        error_code="not_found",
                        message=f"Project {pid} not found or not visible",
                    )
                )
            elif pid not in valid:
                valid.append(pid)

        if valid:
            await self._groups.add_project_refs(group.id, valid)  # pyright: ignore[reportArgumentType]  # id is set on a resolved group
        return BulkWriteSummary(total=len(project_ids), succeeded=valid, failed=failed)

    async def _delete(self, group: ProjectGroupOut, project_ids: list[ShortStr]) -> BulkWriteSummary[str]:
        """Delete requested members from the group; non-members are reported as failed items."""
        current = {(link.ref.id if isinstance(link, Link) else link.id) for link in (group.projects or [])}
        failed: list[BulkFailure] = []
        present: list[ShortStr] = []
        for index, pid in enumerate(project_ids):
            if pid not in current:
                failed.append(
                    BulkFailure(
                        index=index,
                        identifier={"id": pid},
                        error_code="not_found",
                        message=f"Project {pid} is not a member of this group",
                    )
                )
            elif pid not in present:
                present.append(pid)

        if present:
            await self._groups.delete_project_refs(group.id, present)  # pyright: ignore[reportArgumentType]  # id is set on a resolved group
        return BulkWriteSummary(total=len(project_ids), succeeded=present, failed=failed)

    async def add_projects(self, identifiers: dict[str, Any], project_ids: list[ShortStr]) -> BulkWriteSummary[str]:
        """Add projects to the group matching ``identifiers`` (``{"id": ...}`` or ``{"name", "owner"}``)."""
        return await self._add(await self._resolve_one(identifiers), project_ids)

    async def delete_projects(self, identifiers: dict[str, Any], project_ids: list[ShortStr]) -> BulkWriteSummary[str]:
        """Delete projects from the group matching ``identifiers`` (``{"id": ...}`` or ``{"name", "owner"}``)."""
        return await self._delete(await self._resolve_one(identifiers), project_ids)
