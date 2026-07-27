from typing import Any

from pymongo import UpdateOne

from mpcontribs_api.authz import User
from mpcontribs_api.domains._shared.repository import MongoDbRepository
from mpcontribs_api.domains.projects.models import (
    Column,
    Project,
    ProjectFilter,
    ProjectIn,
    ProjectOut,
    ProjectPatch,
    Stats,
)
from mpcontribs_api.exceptions import ConflictError, PermissionError
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

    def __init__(self, user: User) -> None:
        super().__init__(user)
        self._user = user

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

    async def get_project_by_id(self, id: str, fields: frozenset[str] | None):
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

    async def set_stats_and_columns(self, updates: dict[str, tuple[Stats, list[Column]]]) -> None:
        """Overwrite the derived ``stats``/``columns`` of the given projects in one bulk write.

        A **system-computed write**: identity is the project ``_id`` alone and the user scope is
        deliberately not applied. Stats are recomputed from a project's contributions after a write
        (see ``ContributionService.update_project``) and must land even when the caller is a group
        contributor who does not own the project. Missing ids match nothing and are silently skipped.

        Args:
            updates: ``{project_id: (stats, columns)}`` to persist
        """
        if not updates:
            return
        ops = [
            UpdateOne(
                {"_id": pid},
                {
                    "$set": {
                        "stats": stats.model_dump(mode="json"),
                        "columns": [c.model_dump(mode="json") for c in cols],
                    }
                },
            )
            for pid, (stats, cols) in updates.items()
        ]
        await self.document_model.get_pymongo_collection().bulk_write(ops, ordered=False)

    async def insert_project(self, id: str, project: ProjectIn) -> Project:
        """Insert a new project under ``id`` (supplied by the caller), rejecting a duplicate id.

        Projects carry a meaningful ``ShortStr`` id that is not part of the input body, so — unlike
        the generic ``insert_one`` — the id is passed explicitly and stamped onto the document here.
        """
        document = Project.from_input_model(project, id=id)
        existing = await self.document_model.find_one(self.document_model.id == id)
        if existing:
            raise ConflictError(f"Cannot insert document.\n Document with ID {id} exists")
        await document.insert()
        return document

    async def patch_project_by_id(self, id: str, update: ProjectPatch) -> Project:
        """Partially update a project by id, scoped to the current user. See ``patch``.

        ``is_approved`` is an admin-only curation flag: a non-admin that sets it (to any value) is
        rejected. ``stats``/``columns`` are not on the patch model at all, so they cannot be
        client-patched. Both remain server-owned.

        Raises:
            PermissionError: if a non-admin caller sets ``is_approved``
        """
        if update.is_approved is not None and not self._user.is_admin:
            raise PermissionError(required_role="admin")
        return await self.patch(id, update)

    async def delete_project_by_id(self, id: str) -> None:
        """Delete a project by id, scoped to the current user. See ``delete_by_id``."""
        await self.delete_by_id(id)

    async def upsert_project_by_id(self, id: str, data: ProjectIn) -> Project:
        """Upsert a project by provided id, authorized to the current user.

        Update the document if the id exists, otherwise insert a new one under that id.
        Authorization (the read scope is for visibility, not write access, so it is not
        reused here):

        - **Existing project:** only its ``owner`` or an admin may overwrite it. The stored
          ``owner`` is preserved — ownership cannot be reassigned through the request body.
        - **New project:** ``owner`` is forced to the caller, ignoring any body value.

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
        project = self.document_model.from_input_model(data, id=id)
        if existing is not None:
            if not (self._user.is_admin or existing.owner == self._user.username):
                raise PermissionError(required_role="owner-or-admin")
            # Ownership is immutable via upsert; keep the original owner.
            project.owner = existing.owner
            # Server-owned rollups are never taken from the request body; keep the stored values
            # (they self-heal on the next contribution write via ``ContributionService``).
            project.stats = existing.stats
            project.columns = existing.columns
            # Approval is an admin-only curation flag: a non-admin cannot toggle it via a full
            # overwrite, so preserve whatever is already stored.
            if not self._user.is_admin:
                project.is_approved = existing.is_approved
        else:
            # New project is owned by the caller
            project.owner = self._user.username
            # A new project starts unapproved; only an admin may create it pre-approved.
            if not self._user.is_admin:
                project.is_approved = False
        return await project.save()
