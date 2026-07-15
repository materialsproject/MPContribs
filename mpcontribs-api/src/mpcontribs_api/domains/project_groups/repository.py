from typing import Any

from mpcontribs_api.authz import User
from mpcontribs_api.domains._shared.models import DeleteResponse
from mpcontribs_api.domains._shared.repository import MongoDbRepository
from mpcontribs_api.domains._shared.types import PrefixedEmail, SearchStr
from mpcontribs_api.domains.project_groups.models import (
    ProjectGroup,
    ProjectGroupFilter,
    ProjectGroupIn,
    ProjectGroupOut,
    ProjectGroupPatch,
)
from mpcontribs_api.pagination import CursorParams, Page


class ProjectGroupRepository(
    MongoDbRepository[ProjectGroup, ProjectGroupIn, ProjectGroupOut, ProjectGroupFilter, ProjectGroupPatch]
):
    document_model = ProjectGroup
    out_model = ProjectGroupOut

    @staticmethod
    def _build_scope(user: User) -> dict[str, Any]:
        """Provides scope based on current user's permitted groups and publicly released data."""
        if user.is_admin:
            return {}
        ors: list[dict[str, Any]] = [{"is_public": True, "is_approved": True}]
        if not user.is_anonymous:
            ors.append({"owner": user.username})
            if user.groups:
                ors.append({"_id": {"$in": sorted(user.groups)}})
        return {"$or": ors}

    async def get_project_groups(
        self,
        pagination: CursorParams,
        filter: ProjectGroupFilter,
        fields: frozenset[str] | None,
    ) -> Page[ProjectGroupOut]:
        """Return paginated project groups matching a filter.

        Args:
            pagination (CursorParams): arguments for cursor-based pagination
            filter (ProjectGroupFilter): optional filters to select ProjectGroups
            fields (frozenset[str] | None): the fields to return to a user
        """
        return await self.get_many(pagination=pagination, filter=filter, fields=fields)

    async def get_project_group(
        self,
        name: SearchStr,
        owner: PrefixedEmail,
        fields: frozenset[str] | None,
    ) -> ProjectGroupOut | None:
        """Return the single project group identified by ``name`` + ``owner``. See ``get_one``."""
        return await self.get_one({"name": name, "owner": owner}, fields)

    async def insert_project_group(self, project_group: ProjectGroupIn) -> ProjectGroup:
        return await self.insert_one(in_resource=project_group)

    async def patch_project_group(
        self, name: SearchStr, owner: PrefixedEmail, update: ProjectGroupPatch
    ) -> ProjectGroup:
        """Patch the single project group identified by ``name`` + ``owner``. See ``patch_one``."""
        return await self.patch_one({"name": name, "owner": owner}, update)

    async def delete_project_group(self, name: SearchStr, owner: PrefixedEmail) -> DeleteResponse:
        """Delete the single project group identified by ``name`` + ``owner``. See ``delete_one``."""
        return await self.delete_one({"name": name, "owner": owner})

    async def delete_project_groups(self, filter: ProjectGroupFilter) -> DeleteResponse:
        """Bulk-delete every scoped project group matching ``filter``. See ``delete``."""
        return await self.delete(filter)
