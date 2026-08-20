from typing import Any

from beanie import PydanticObjectId, UpdateResponse
from beanie.operators import AddToSet, Pull
from bson import DBRef
from pymongo.asynchronous.client_session import AsyncClientSession

from mpcontribs_api.domains._shared.models import DeleteResponse
from mpcontribs_api.domains._shared.repository import MongoDbRepository
from mpcontribs_api.domains._shared.types import ShortStr
from mpcontribs_api.domains.project_groups.models import (
    ProjectGroup,
    ProjectGroupFilter,
    ProjectGroupIn,
    ProjectGroupOut,
    ProjectGroupPatch,
)
from mpcontribs_api.exceptions import NotFoundError, PermissionError
from mpcontribs_api.scope import Owned, Public, RoleIn, Scope


class ProjectGroupRepository(
    MongoDbRepository[ProjectGroup, ProjectGroupIn, ProjectGroupOut, ProjectGroupFilter, ProjectGroupPatch]
):
    document_model = ProjectGroup
    out_model = ProjectGroupOut
    # Visible when public, owned by the caller, or granted via a ``project-group:<oid>`` role (keyed
    # on ``_id``). Project groups have no approval flag. Roles arrive as raw hex strings, so the id
    # clause coerces each to ``PydanticObjectId`` (malformed values are dropped by ``RoleIn``). Admins
    # bypass scope (handled by ``Scope``).
    read_scope = Scope(Public(), Owned(), RoleIn("_id", "project_group_roles", coerce=PydanticObjectId))

    async def delete_one(
        self, identifiers: dict[str, Any], session: AsyncClientSession | None = None
    ) -> DeleteResponse:
        """Delete the single project group matching ``identifiers`` (``{name, owner}`` or ``{id}``).O
        Absence (in scope) takes precedence over the ownership gate: a non-admin may only delete
        their own group, so deleting another owner's visible (public) group is forbidden rather
        than silently a no-op. The ``name`` + ``owner`` unique index makes the match unambiguous.
        The auth check runs against the resolved document; the write is delegated to the base
        :meth:`MongoDbRepository.delete_one`.
        """
        doc = await self.document_model.find_one(self._scope, self._identifier_query(identifiers), session=session)  # pyright: ignore[reportArgumentType]
        if doc is None:
            raise NotFoundError(f"{self.document_model.__name__} not found", **identifiers)
        if not (self._user.is_admin or doc.owner == self._user.username):
            raise PermissionError(required_role="owner-or-admin")
        return await super().delete_one(identifiers, session=session)

    async def delete_many(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, filter: ProjectGroupFilter, session: AsyncClientSession | None = None
    ) -> DeleteResponse:
        """Bulk-delete project groups matching ``filter``, restricted to the caller's own.

        A non-admin's bulk delete is scoped to their own groups (overriding any ``owner`` in the
        filter) so it can never remove public groups belonging to others. The write is delegated to
        the base :meth:`MongoDbRepository.delete_many`.
        """
        if not self._user.is_admin:
            filter.owner = self._user.username
        return await super().delete_many(filter, session=session)

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
