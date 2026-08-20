from beanie import PydanticObjectId, UpdateResponse
from beanie.operators import AddToSet, Pull
from bson import DBRef
from pymongo.asynchronous.client_session import AsyncClientSession

from mpcontribs_api.domains._shared.repository import MongoDbRepository
from mpcontribs_api.domains._shared.types import ShortStr
from mpcontribs_api.domains.project_groups.models import (
    ProjectGroup,
    ProjectGroupFilter,
    ProjectGroupIn,
    ProjectGroupOut,
    ProjectGroupPatch,
)
from mpcontribs_api.scope import Owned, Public, RoleIn, Scope


class ProjectGroupRepository(
    MongoDbRepository[ProjectGroup, ProjectGroupIn, ProjectGroupOut, ProjectGroupFilter, ProjectGroupPatch]
):
    """Query/persistence toolbox for project groups."""

    document_model = ProjectGroup
    out_model = ProjectGroupOut
    # Visible when public, owned by the caller, or granted via a ``project-group:<oid>`` role (keyed
    # on ``_id``). Project groups have no approval flag. Roles arrive as raw hex strings, so the id
    # clause coerces each to ``PydanticObjectId`` (malformed values are dropped by ``RoleIn``). Admins
    # bypass scope (handled by ``Scope``).
    read_scope = Scope(Public(), Owned(), RoleIn("_id", "project_group_roles", coerce=PydanticObjectId))

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
