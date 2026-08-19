from typing import Any

from beanie import PydanticObjectId
from pymongo import UpdateOne
from pymongo.asynchronous.client_session import AsyncClientSession

from mpcontribs_api.authz import User
from mpcontribs_api.domains._shared.models import DeleteResponse
from mpcontribs_api.domains._shared.repository import MongoDbRepository
from mpcontribs_api.domains.consumers.models import ConsumerSettings
from mpcontribs_api.domains.projects.models import (
    Column,
    Project,
    ProjectFilter,
    ProjectIn,
    ProjectOut,
    ProjectPatch,
    Stats,
)
from mpcontribs_api.exceptions import ConflictError, NotFoundError, PermissionError, ValidationError
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

    def __init__(self, user: User, limits: ConsumerSettings | None = None) -> None:
        super().__init__(user)
        self._user = user
        self._limits = limits or ConsumerSettings()

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

    async def _check_num_projects(self, owner: str):
        """Reject a *new* project that would push ``owner`` past the per-user cap."""
        max_projects = self._limits.max_projects
        # Soft limit: this count-then-insert is not atomic, so concurrent creates by the same owner
        # can overshoot the cap by a bounded amount. Acceptable for an anti-abuse quota.
        result = await Project.find(Project.owner == owner).count()
        if result >= max_projects:
            raise PermissionError(
                f"Cannot be owner of more than {max_projects} projects",
                owner=owner,
                num_projects=result,
            )

    async def get_projects(
        self,
        filter: ProjectFilter,
        pagination: CursorParams,
        fields: frozenset[str] | None,
    ):
        """Query the Project collection, scoped to the current user. See ``get_many``."""
        return await self.get_many(pagination=pagination, filter=filter, fields=fields)

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

    async def insert_project(self, id: str, project: ProjectIn) -> Project:
        """Insert a new project under ``id`` (supplied by the caller), rejecting a duplicate id.

        Projects carry a meaningful ``ShortStr`` id that is not part of the input body, so — unlike
        the generic ``insert_one`` — the id is passed explicitly and stamped onto the document here.
        """
        await self._check_num_projects(project.owner)
        document = Project.from_input_model(project, id=id)
        existing = await self.document_model.find_one(self.document_model.id == id)
        if existing:
            raise ConflictError(f"Cannot insert document.\n Document with ID {id} exists")
        await document.insert()
        return document

    async def patch_one(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        identifiers: dict[str, Any],
        update: ProjectPatch,
        session: AsyncClientSession | None = None,
        extra_set: dict[str, Any] | None = None,
    ) -> Project:
        """Partially update a scoped project by id, enforcing approval rules.

        - Only an admin may change ``is_approved``.
        - Resulting state must satisfy is_public <-> is_approved condition

        The ``initiative`` field is split out upstream in ``ProjectService.patch_one``, so it never
        reaches this method as a bare slug; an assignment that also edits plain fields arrives with
        the resolved link passed through ``extra_set`` (``{"initiative": <DBRef | None>}``) and is
        written together with the plain fields in the single ``$set``.
        """
        await self._enforce_patch_rules(identifiers["id"], update)
        return await super().patch_one(identifiers, update, session=session, extra_set=extra_set)

    async def _enforce_patch_rules(self, id: str, update: ProjectPatch) -> None:
        """Enforce project patch invariants against the scoped target.

        - Only an admin may change ``is_approved``.
        - The resulting state must satisfy the is_public -> is_approved condition.

        Raises ``NotFoundError`` when the project is invisible to the caller or absent, so both the
        plain and initiative-bearing patch paths reject unseen documents identically.
        """
        data = update.model_dump(exclude_unset=True)
        if "is_approved" in data and not self._user.is_admin:
            raise PermissionError(required_role="admin")

        existing = await self.document_model.find_one(self._scope, self.document_model.id == id)
        if existing is None:
            raise NotFoundError(f"{self.document_model.__name__} not found", id=id)

        resulting_approved = data.get("is_approved", existing.is_approved)
        resulting_public = data.get("is_public", existing.is_public)
        if resulting_public and not resulting_approved:
            raise ValidationError("a project cannot be public until it is approved", id=id)

    async def delete_one(
        self, identifiers: dict[str, Any], session: AsyncClientSession | None = None
    ) -> DeleteResponse:
        """Delete a scoped project by id. Restricted to the owner or an admin.

        Visibility (public/approved or group membership) is not enough to delete: a project can
        only be dissolved by its owner (or an admin). A caller who cannot see the project gets a
        404; a caller who can see it but does not own it gets a 403. The auth check runs against the
        resolved document; the write is delegated to the base :meth:`MongoDbRepository.delete_one`.
        """
        id = identifiers["id"]
        existing = await self.document_model.find_one(self._scope, self._identifier_query({"id": id}))
        if existing is None:
            raise NotFoundError(f"{self.document_model.__name__} not found", id=id)
        if not (self._user.is_admin or existing.owner == self._user.username):
            raise PermissionError(required_role="owner-or-admin")
        return await super().delete_one(identifiers, session=session)

    async def upsert_one(self, identifiers: dict[str, Any], data: ProjectIn) -> Project:
        """Upsert a project by provided id, authorized to the current user.

        Update the document if the id exists, otherwise insert a new one under that id.

        - **Existing project:** only its ``owner`` or an admin may overwrite it. The stored
          ``owner`` and all server-managed fields (see ``Project.server_managed_fields``) are
          preserved - ``ProjectIn`` cannot carry them, so a PUT never resets approval, publication,
          or stats.
        - **New project:** ``owner`` is forced to the caller; server-managed fields keep their
          defaults

        Note: relies on the identifier ``id`` for identity, not the body's id.

        Args:
            identifiers (dict[str, Any]): the identifier of the project to upsert (``{"id": ...}``)
            data (ProjectIn): the data of the project to upsert

        Returns:
            Project: the full document that either replaced an old one or was inserted

        Raises:
            PermissionError: if a non-owner, non-admin caller targets an existing project
        """
        # The route enforces authentication, so an anonymous caller should never reach here.
        if self._user.username is None:
            raise PermissionError(required_role="authenticated")

        id = identifiers["id"]
        # ``columns`` are server-owned (derived from contributions) and absent from ProjectIn, so
        # there is no client-supplied column set to cap on the write path.
        existing = await self.document_model.find_one(self.document_model.id == id)
        project = self.document_model.from_input_model(data, id=id)
        if existing is not None:
            if not (self._user.is_admin or existing.owner == self._user.username):
                raise PermissionError(required_role="owner-or-admin")
            # Ownership is immutable via upsert; keep the original owner. Updating an existing
            # project does not create a new one, so the per-user project cap does not apply.
            project.owner = existing.owner
            # make sure a full replacement doesn't overwrite server-defined fields
            for field in self.document_model.server_managed_fields():
                setattr(project, field, getattr(existing, field))
            # Server-owned rollups are never taken from the request body; keep the stored values
            # (they self-heal on the next contribution write via ``ContributionService``).
            project.stats = existing.stats
            project.columns = existing.columns
            # Approval is an admin-only curation flag: a non-admin cannot toggle it via a full
            # overwrite, so preserve whatever is already stored.
            if not self._user.is_admin:
                project.is_approved = existing.is_approved
        else:
            # New project: the caller owns it, regardless of the submitted owner. Enforce the
            # per-user cap against the caller before creating another project under their name.
            project.owner = self._user.username
            # Approval is admin-only; a non-admin's new project always starts unapproved.
            if not self._user.is_admin:
                project.is_approved = False
            await self._check_num_projects(self._user.username)

        if project.is_public and not project.is_approved:
            raise ValidationError("a project cannot be public until it is approved", id=id)
        return await project.save()

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
