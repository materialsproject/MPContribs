from typing import Any

from beanie import PydanticObjectId
from pymongo import UpdateOne

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
from mpcontribs_api.scope import Owned, Public, RoleIn, Scope


class MongoDbProjectRepository(MongoDbRepository[Project, ProjectIn, ProjectOut, ProjectFilter, ProjectPatch]):
    """A repository layer for access to MongoDB.

    Attributes:
        _scope (dict[str, Any]): additional terms to inject into mongo queries to enforce user
            authorization on resources
    """

    document_model = Project
    out_model = ProjectOut
    # Visible when public+approved, owned by the caller, or granted as a bare project role (its
    # ``_id``). Admins bypass scope (handled by ``Scope``).
    read_scope = Scope(Public(approved=True), Owned(), RoleIn("_id", "project_roles"))

    async def count_for_owner(self, owner: str) -> int:
        """Count projects owned by ``owner``, ignoring user scope."""
        return await self.document_model.find(self.document_model.owner == owner).count()

    async def find_by_id_unscoped(self, id: str) -> Project | None:
        """Return the project with ``id`` regardless of user scope, or ``None`` if absent.

        The upsert path uses this to decide insert-vs-replace: a caller must not be able to "create"
        a project over an id that already exists but is invisible to them, so existence is checked
        without the scope filter. The service authorizes the write against the returned document.
        """
        return await self.document_model.find_one(self.document_model.id == id)

    async def unique_columns_by_id(self, ids: list[str]) -> dict[str, str | None]:
        """Return ``{project_id: unique_column}`` for the given project ids, scoped to the user.

        Used by the contribution write path to resolve each project's identity discriminator in one
        round-trip instead of fetching each project separately. ``unique_column`` is ``None`` when the
        project sets none (identity is then the fixed-field triple). Projects the user cannot see (or
        that do not exist) are simply absent from the result, so the caller can treat them as
        inaccessible.

        Args:
            ids: project ids to look up

        Returns:
            dict[str, str | None]: mapping of project id to its ``unique_column`` (or ``None``)
        """
        if not ids:
            return {}
        query: dict[str, Any] = {"_id": {"$in": ids}}
        if self._scope:
            query = {"$and": [self._scope, query]}
        collection = self.document_model.get_pymongo_collection()
        result: dict[str, str | None] = {}
        async for doc in collection.find(query, {"unique_column": 1}):
            result[doc["_id"]] = doc.get("unique_column")
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

    async def clear_initiative_refs(self, initiative_id: PydanticObjectId) -> int:
        """Unset the ``initiative`` link on every project pointing at ``initiative_id``.

        Args:
            initiative_id (PydanticObjectId): the deleted initiative whose back-references to clear
        """
        collection = self.document_model.get_pymongo_collection()
        result = await collection.update_many(
            {"initiative.$id": initiative_id},
            {"$set": {"initiative": None}},
        )
        return result.modified_count
