from beanie import Link

from mpcontribs_api.domains._shared.bulk import BulkFailure, BulkWriteSummary
from mpcontribs_api.domains._shared.types import PrefixedEmail, SearchStr, ShortStr
from mpcontribs_api.domains.project_groups.models import ProjectGroupOut
from mpcontribs_api.domains.project_groups.repository import ProjectGroupRepository
from mpcontribs_api.domains.projects.repository import MongoDbProjectRepository
from mpcontribs_api.exceptions import NotFoundError

# Fields the membership operations need off a resolved group: its id (target of the update) and its
# current members (so deletion can tell members from non-members).
_GROUP_FIELDS = frozenset({"id", "projects"})


class ProjectGroupService:
    """Coordinates project-group membership changes across the groups and projects collections"""

    def __init__(
        self,
        groups: ProjectGroupRepository,
        projects: MongoDbProjectRepository,
    ) -> None:
        self._groups = groups
        self._projects = projects

    async def _resolve_by_id(self, group_id: str) -> ProjectGroupOut:
        """Resolve a visible group by its ObjectId, or raise ``NotFoundError``."""
        oid = self._groups._convert_object_id(group_id)
        group = await self._groups.get_by_id(oid, fields=_GROUP_FIELDS)
        if group is None:
            raise NotFoundError("ProjectGroup not found", id=group_id)
        return group  # pyright: ignore[reportReturnType]  # projected reads return the out model

    async def _resolve_by_identifiers(self, name: SearchStr, owner: PrefixedEmail) -> ProjectGroupOut:
        """Resolve a visible group by its ``(name, owner)`` identifiers, or raise ``NotFoundError``.

        Propagates ``ConflictError`` from the repository if the identifiers are ambiguous.
        """
        group = await self._groups.get_one({"name": name, "owner": owner}, fields=_GROUP_FIELDS)
        if group is None:
            raise NotFoundError("ProjectGroup not found", name=name, owner=owner)
        return group

    async def _add(self, group: ProjectGroupOut, project_ids: list[ShortStr]) -> BulkWriteSummary[str]:
        """Validate each project against the projects collection, then add the valid ones.

        A project that does not exist or is not visible to the caller is reported as a failed item;
        the rest are added in a single atomic ``$addToSet`` (idempotent for existing members).
        """
        failed: list[BulkFailure] = []
        valid: list[ShortStr] = []
        for index, pid in enumerate(project_ids):
            if await self._projects.get_by_id(pid, fields=frozenset({"id"})) is None:
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
        current = {
            (link.ref.id if isinstance(link, Link) else link.id) for link in (group.projects or [])
        }
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

    async def add_projects_by_id(self, group_id: str, project_ids: list[ShortStr]) -> BulkWriteSummary[str]:
        """Add projects to the group identified by ``group_id``."""
        return await self._add(await self._resolve_by_id(group_id), project_ids)

    async def add_projects_by_identifiers(
        self, name: SearchStr, owner: PrefixedEmail, project_ids: list[ShortStr]
    ) -> BulkWriteSummary[str]:
        """Add projects to the group identified by ``(name, owner)``."""
        return await self._add(await self._resolve_by_identifiers(name, owner), project_ids)

    async def delete_projects_by_id(self, group_id: str, project_ids: list[ShortStr]) -> BulkWriteSummary[str]:
        """Delete projects from the group identified by ``group_id``."""
        return await self._delete(await self._resolve_by_id(group_id), project_ids)

    async def delete_projects_by_identifiers(
        self, name: SearchStr, owner: PrefixedEmail, project_ids: list[ShortStr]
    ) -> BulkWriteSummary[str]:
        """Delete projects from the group identified by ``(name, owner)``."""
        return await self._delete(await self._resolve_by_identifiers(name, owner), project_ids)
