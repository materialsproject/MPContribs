from typing import Any

from beanie import PydanticObjectId, UpdateResponse
from beanie.operators import AddToSet, Pull
from bson import DBRef
from bson.errors import InvalidId
from pymongo.asynchronous.client_session import AsyncClientSession

from mpcontribs_api.authz import User
from mpcontribs_api.domains._shared.models import DeleteResponse
from mpcontribs_api.domains._shared.repository import MongoDbRepository
from mpcontribs_api.domains._shared.types import PrefixedEmail, SearchStr, ShortStr
from mpcontribs_api.domains.project_groups.models import (
    ProjectGroup,
    ProjectGroupFilter,
    ProjectGroupIn,
    ProjectGroupOut,
    ProjectGroupPatch,
)
from mpcontribs_api.exceptions import NotFoundError, PermissionError
from mpcontribs_api.pagination import CursorParams, Page


class ProjectGroupRepository(
    MongoDbRepository[ProjectGroup, ProjectGroupIn, ProjectGroupOut, ProjectGroupFilter, ProjectGroupPatch]
):
    document_model = ProjectGroup
    out_model = ProjectGroupOut

    @staticmethod
    def _build_scope(user: User) -> dict[str, Any]:
        """Scope reads to what the caller may see: public groups, ones they own, or ones granted."""
        if user.is_admin:
            return {}
        ors: list[dict[str, Any]] = [{"is_public": True}]
        if not user.is_anonymous:
            ors.append({"owner": user.username})
            granted: list[PydanticObjectId] = []
            for raw in user.project_group_roles:
                try:
                    granted.append(PydanticObjectId(raw))
                except InvalidId:
                    continue
            if granted:
                ors.append({"_id": {"$in": sorted(granted)}})
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
        """Delete the single project group identified by ``name`` + ``owner``."""
        oid = await self._resolve_one_id({"name": name, "owner": owner})
        if oid is None:
            raise NotFoundError(f"{self.document_model.__name__} not found", name=name, owner=owner)
        if not (self._user.is_admin or owner == self._user.username):
            raise PermissionError(required_role="owner-or-admin")
        return await self.delete_by_id(oid)

    async def delete_project_groups(self, filter: ProjectGroupFilter) -> DeleteResponse:
        """Bulk-delete project groups matching ``filter``, restricted to the caller's own.

        A non-admin's bulk delete is scoped to their own groups (overriding any ``owner`` in the
        filter) so it can never remove public groups belonging to others. See ``delete``.
        """
        if not self._user.is_admin:
            filter.owner = self._user.username
        return await self.delete(filter)

    async def add_project_refs(
        self,
        group_id: PydanticObjectId,
        project_ids: list[ShortStr],
        session: AsyncClientSession | None = None,
    ) -> ProjectGroup | None:
        """Atomically add project references to a scoped group, deduplicating existing members.

        Args:
            group_id (PydanticObjectId): the id of the group to modify
            project_ids (list[ShortStr]): project ids to add (already validated by the service)
            session (AsyncClientSession | None): optional client session for transactions
        """
        refs = [DBRef("projects", pid) for pid in project_ids]
        query = self.document_model.find_one(self._scope, self.document_model.id == group_id, session=session).update(
            AddToSet({"projects": {"$each": refs}}),
            response_type=UpdateResponse.NEW_DOCUMENT,
        )
        return await query  # pyright: ignore[reportGeneralTypeIssues] # beanie UpdateQuery is awaitable

    async def delete_project_refs(
        self,
        group_id: PydanticObjectId,
        project_ids: list[ShortStr],
        session: AsyncClientSession | None = None,
    ) -> ProjectGroup | None:
        """Atomically delete project references from a scoped group.

        Args:
            group_id (PydanticObjectId): the id of the group to modify
            project_ids (list[ShortStr]): project ids to delete
            session (AsyncClientSession | None): optional client session for transactions
        """
        refs = [DBRef("projects", pid) for pid in project_ids]
        query = self.document_model.find_one(self._scope, self.document_model.id == group_id, session=session).update(
            Pull({"projects": {"$in": refs}}),
            response_type=UpdateResponse.NEW_DOCUMENT,
        )
        return await query  # pyright: ignore[reportGeneralTypeIssues] # beanie UpdateQuery is awaitable
