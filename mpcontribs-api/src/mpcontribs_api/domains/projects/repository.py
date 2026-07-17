from typing import Any

from beanie import PydanticObjectId, UpdateResponse
from beanie.operators import Set
from bson import DBRef

from mpcontribs_api.authz import User
from mpcontribs_api.domains._shared.repository import MongoDbRepository
from mpcontribs_api.domains.projects.models import (
    Project,
    ProjectFilter,
    ProjectIn,
    ProjectOut,
    ProjectPatch,
)
from mpcontribs_api.exceptions import NotFoundError, PermissionError, ValidationError
from mpcontribs_api.pagination import CursorParams


class MongoDbProjectRepository(MongoDbRepository[Project, ProjectIn, ProjectOut, ProjectFilter, ProjectPatch]):
    """A repository layer for access to MongoDB.

    This is the layer that directly interacts with database operations. Shared CRUD logic lives on
    :class:`MongoDbRepository`; the methods here are domain-named forwarders that give routers a
    consistent vocabulary and concrete types, plus the operations whose shape is genuinely
    project-specific (id-keyed upsert).

    Attributes:
        _scope (dict[str, Any]): additional terms to inject into mongo queries to enforce user
            authorization on resources
    """

    document_model = Project
    out_model = ProjectOut

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

    async def get_projects(
        self,
        filter: ProjectFilter,
        pagination: CursorParams,
        fields: frozenset[str] | None,
    ):
        """Query the Project collection, scoped to the current user. See ``get_many``."""
        return await self.get_many(pagination=pagination, filter=filter, fields=fields)

    async def get_project_by_id(self, id: str, fields: frozenset[str] | None) -> Project | ProjectOut | None:
        """Find a single project by id, scoped to the current user. See ``get_by_id``."""
        return await self.get_by_id(id, fields)

    async def unique_identifiers_by_id(self, ids: list[str]) -> dict[str, bool]:
        """Return ``{project_id: unique_identifiers}`` for the given project ids, scoped to the user.

        Used by the contribution write path to apply per-project version rules in one round-trip
        instead of fetching each project separately. Projects the user cannot see (or that do not
        exist) are simply absent from the result, so the caller can treat them as inaccessible.

        Args:
            ids: project ids to look up

        Returns:
            dict[str, bool]: mapping of project id to its ``unique_identifiers`` flag
        """
        if not ids:
            return {}
        query: dict[str, Any] = {"_id": {"$in": ids}}
        if self._scope:
            query = {"$and": [self._scope, query]}
        collection = self.document_model.get_pymongo_collection()
        result: dict[str, bool] = {}
        async for doc in collection.find(query, {"unique_identifiers": 1}):
            result[doc["_id"]] = bool(doc.get("unique_identifiers"))
        return result

    async def insert_project(self, project: ProjectIn) -> Project:
        """Insert a new project, rejecting a duplicate id. See ``insert_one``."""
        return await self.insert_one(project)

    async def patch_project_by_id(self, id: str, update: ProjectPatch) -> Project:
        """Partially update a scoped project by id, enforcing approval rules.

        - Only an admin may change ``is_approved``.
        - Resulting state must satisfy is_public <-> is_approved condition

        The ``initiative`` field is split out upstream in ``ProjectService.patch``, so it never
        reaches this method.
        """
        data = update.model_dump(exclude_unset=True)
        if "is_approved" in data and not self._user.is_admin:
            raise PermissionError(required_role="admin")

        existing = await self.document_model.find_one(self._scope, self.document_model.id == id)
        if existing is None:
            raise NotFoundError(self._not_found(id))

        resulting_approved = data.get("is_approved", existing.is_approved)
        resulting_public = data.get("is_public", existing.is_public)
        if resulting_public and not resulting_approved:
            raise ValidationError("a project cannot be public until it is approved", id=id)

        return await self.patch(id, update)

    async def delete_project_by_id(self, id: str) -> None:
        """Delete a scoped project by id. Restricted to the owner or an admin.

        Visibility (public/approved or group membership) is not enough to delete: a project can
        only be dissolved by its owner (or an admin). A caller who cannot see the project gets a
        404; a caller who can see it but does not own it gets a 403.
        """
        existing = await self.document_model.find_one(self._scope, self.document_model.id == id)
        if existing is None:
            raise NotFoundError(self._not_found(id))
        if not (self._user.is_admin or existing.owner == self._user.username):
            raise PermissionError(required_role="owner-or-admin")
        await self.delete_by_id(id)

    async def upsert_project_by_id(self, id: str, data: ProjectIn) -> Project:
        """Upsert a project by provided id, authorized to the current user.

        Update the document if the id exists, otherwise insert a new one under that id.

        - **Existing project:** only its ``owner`` or an admin may overwrite it. The stored
          ``owner`` is preserved - ownership cannot be reassigned through the request body.
        - **New project:** ``owner`` is forced to the caller, ignoring any body value.

        an existing project keeps its stored approval and a new one starts unapproved. The resulting
        document must also satisfy ``is_public ⇒ is_approved``.

        Note: relies on the path param ``id`` for identity, not the body's id.

        Args:
            id (str): the id of the project to upsert
            data (ProjectIn): the data of the project to upsert

        Returns:
            Project: the full document that either replaced an old one or was inserted

        Raises:
            PermissionError: if a non-owner, non-admin caller targets an existing project
        """
        # The route enforces authentication, so an anonymous caller should never reach here.
        if self._user.username is None:
            raise PermissionError(required_role="authenticated")

        existing = await self.document_model.find_one(self.document_model.id == id)
        project = self.document_model.from_input_model(data)
        project.id = id
        if existing is not None:
            if not (self._user.is_admin or existing.owner == self._user.username):
                raise PermissionError(required_role="owner-or-admin")
            # Ownership is immutable via upsert; keep the original owner.
            project.owner = existing.owner
            # Approval is admin-only; a non-admin keeps the project's stored approval state.
            if not self._user.is_admin:
                project.is_approved = existing.is_approved
        else:
            # New project: the caller owns it, regardless of the submitted owner.
            project.owner = self._user.username
            # Approval is admin-only; a non-admin's new project always starts unapproved.
            if not self._user.is_admin:
                project.is_approved = False

        if project.is_public and not project.is_approved:
            raise ValidationError("a project cannot be public until it is approved", id=id)
        return await project.save()

    async def set_initiative(self, id: str, ref: DBRef | None) -> Project:
        """Set a scoped project's canonical initiative link.

        The link is written as-is (a ``DBRef`` into ``initiatives`` or ``None``); all authorization
        and limit checks are the caller's (see ``ProjectInitiativeService``). Scoping ensures a
        project the caller cannot see is reported as not found rather than silently missed.

        Args:
            id (str): the id of the project to update
            ref (DBRef | None): the initiative reference to assign, or None to unassign
        """
        query = self.document_model.find_one(self._scope, self.document_model.id == id).update(
            Set({"initiative": ref}),
            response_type=UpdateResponse.NEW_DOCUMENT,
        )
        updated = await query  # pyright: ignore[reportGeneralTypeIssues] # beanie UpdateQuery is awaitable
        if updated is None:
            raise NotFoundError(self._not_found(id))
        return updated

    async def count_initiative_members(self, initiative_id: PydanticObjectId, exclude_project_id: str | None) -> int:
        """Count projects assigned to an initiative, ignoring user scope.

        The unapproved-initiative member limit is an integrity constraint on the initiative's true
        size, so it must count every member regardless of who can see them — a scoped count could
        let a collaborator overshoot the cap with projects they cannot see. ``exclude_project_id``
        drops the project being (re)assigned so re-assigning an existing member is idempotent and
        never trips the limit.

        Args:
            initiative_id (PydanticObjectId): the initiative whose members to count
            exclude_project_id (str | None): a project id to exclude from the count, if any
        """
        collection = self.document_model.get_pymongo_collection()
        query: dict[str, Any] = {"initiative.$id": initiative_id}
        if exclude_project_id is not None:
            query["_id"] = {"$ne": exclude_project_id}
        return await collection.count_documents(query)
