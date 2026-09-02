from typing import Any

from bson import DBRef

from mpcontribs_api.authz import INITIATIVE_PATH, ROOT_PATH, User
from mpcontribs_api.config import get_settings
from mpcontribs_api.domains._shared.models import DeleteResponse
from mpcontribs_api.domains.consumers.models import ConsumerSettings
from mpcontribs_api.domains.initiatives.repository import MongoDbInitiativeRepository
from mpcontribs_api.domains.projects.models import Project, ProjectFilter, ProjectIn, ProjectOut, ProjectPatch
from mpcontribs_api.domains.projects.repository import MongoDbProjectRepository
from mpcontribs_api.exceptions import ConflictError, NotFoundError, PermissionError, ValidationError
from mpcontribs_api.pagination import CursorParams, Page


class ProjectService:
    """Owns project write policy and coordinates initiative assignment."""

    def __init__(
        self,
        user: User,
        projects: MongoDbProjectRepository,
        initiatives: MongoDbInitiativeRepository,
        limits: ConsumerSettings | None = None,
    ) -> None:
        self._user = user
        self._projects = projects
        self._initiatives = initiatives
        self._initiative_limits = get_settings().domain.initiatives
        self._consumer_limits = limits or ConsumerSettings()

    async def read_many(
        self, filter: ProjectFilter, pagination: CursorParams, fields: frozenset[str] | None
    ) -> Page[ProjectOut]:
        """Return a page of scoped projects matching ``filter``."""
        return await self._projects.read_many(filter=filter, pagination=pagination, fields=fields)

    async def read_one(self, identifiers: dict[str, Any], fields: frozenset[str] | None) -> Project | ProjectOut | None:
        """Return the single scoped project matching ``identifiers`` (``{"id": ...}``)."""
        return await self._projects.read_one(identifiers, fields)

    async def upsert_one(self, identifiers: dict[str, Any], data: ProjectIn) -> Project:
        """Upsert a project by id, applying every write-policy decision before persisting.

        Update the document if the id exists, otherwise insert a new one under that id.

        - **Existing project:** only its ``owner`` or an admin may overwrite it. The stored ``owner``
          and all server-managed fields (see ``Project.server_managed_fields``) are preserved, so a
          PUT never resets approval, publication, or stats.
        - **New project:** ``owner`` is forced to the caller, approval starts off for non-admins, and
          the per-user cap is enforced against the caller.

        Raises:
            PermissionError: anonymous caller, or a non-owner/non-admin targeting an existing project
            ConflictError: a new project would push the caller past the per-user project cap
            ValidationError: the resulting project would be public while unapproved
        """
        # The route enforces authentication, so an anonymous caller should never reach here.
        if self._user.username is None:
            raise PermissionError(required_role="authenticated")

        id = identifiers["id"]
        existing = await self._projects.find_by_id_unscoped(id)
        project = self._projects.document_model.from_input_model(data, id=id)

        if existing is not None:
            if not (self._user.is_admin(*ROOT_PATH) or existing.owner == self._user.username):
                raise PermissionError(required_role="owner-or-admin")
            # Ownership is immutable via upsert; keep the original owner.
            project.owner = existing.owner
            # A full replacement must not overwrite server-defined fields.
            for field in self._projects.document_model.server_managed_fields():
                setattr(project, field, getattr(existing, field))
            # Server owned calculated fields are not taken from request body
            project.stats = existing.stats
            project.columns = existing.columns
            # Approval is an admin-only flag
            if not self._user.is_admin(*ROOT_PATH):
                project.is_approved = existing.is_approved
        else:
            # New project: the caller owns it, regardless of the submitted owner.
            project.owner = self._user.username
            # Approval is admin-only; a non-admin's new project always starts unapproved.
            if not self._user.is_admin(*ROOT_PATH):
                project.is_approved = False
            await self._enforce_project_cap(self._user.username)

        if project.is_public and not project.is_approved:
            raise ValidationError("a project cannot be public until it is approved", id=id)
        return await self._projects.replace_one(id, project)

    async def update_one(self, identifiers: dict[str, Any], update: ProjectPatch) -> Project:
        """Apply a project patch, enforcing approval rules and routing ``initiative`` changes.

        The approval rules (admin-only ``is_approved``, ``public ⇒ approved``) are checked against the
        scoped target before any write.
        """
        id = identifiers["id"]
        await self._enforce_patch_rules(id, update)

        if "initiative" not in update.model_fields_set:
            return await self._projects.update_one(identifiers, update)

        data = update.model_dump(exclude_unset=True)
        slug = data.pop("initiative", None)

        # Resolve the target link (and run the both-rights + limit checks) before touching anything.
        ref = await self._resolve_initiative_assignment(project_id=id, slug=slug)

        # `initiative` is server derived, so ProjectPatch can't handle it (expects str), so hand it in extra_set
        return await self._projects.update_one(identifiers, ProjectPatch(**data), extra_set={"initiative": ref})

    async def delete_one(self, identifiers: dict[str, Any]) -> DeleteResponse:
        """Delete a scoped project by id. Restricted to the owner or an admin.

        Project must be deleted by an owner or admin. A caller who cannot see the project gets a 404; a
        caller who can see it but does not own it gets a 403.
        """
        existing = await self._projects.read_one(identifiers)
        if existing is None:
            raise NotFoundError("Project not found", **identifiers)
        if not (self._user.is_admin(*ROOT_PATH) or existing.owner == self._user.username):
            raise PermissionError(required_role="owner-or-admin")
        return await self._projects.delete_one(identifiers)

    async def _enforce_project_cap(self, owner: str) -> None:
        """Reject a *new* project that would push ``owner`` past the per-user cap.

        Soft limit: the count-then-insert is not atomic, so concurrent creates by the same owner can
        overshoot the cap slightly.
        """
        max_projects = self._consumer_limits.max_projects
        # Unscoped: the per-owner cap is a property of the owner, independent of who is asking.
        count = await self._projects.count_matching({"owner": owner}, scoped=False)
        if count >= max_projects:
            raise PermissionError(
                f"Cannot be owner of more than {max_projects} projects",
                owner=owner,
                num_projects=count,
            )

    async def _enforce_patch_rules(self, id: str, update: ProjectPatch) -> None:
        """Enforce project patch invariants against the scoped target.

        - Only the project's owner or an admin may patch it. Read visibility (public/approved or a
          project role grant) is not enough to write, mirroring ``upsert_one`` and ``delete_one``.
        - Only an admin may change ``is_approved``.
        - The resulting state must satisfy the ``is_public ⇒ is_approved`` condition.

        Raises ``NotFoundError`` when the project is invisible to the caller or absent, so both the
        plain and initiative-bearing patch paths reject unseen documents identically. A caller who
        can see the project but does not own it gets a ``PermissionError`` (403).
        """
        data = update.model_dump(exclude_unset=True)
        if "is_approved" in data and not self._user.is_admin(*ROOT_PATH):
            raise PermissionError(required_role="admin")

        existing = await self._projects.read_one({"id": id})
        if existing is None:
            raise NotFoundError("Project not found", id=id)
        if not (self._user.is_admin(*ROOT_PATH) or existing.owner == self._user.username):
            raise PermissionError(required_role="owner-or-admin")

        resulting_approved = data.get("is_approved", existing.is_approved)
        resulting_public = data.get("is_public", existing.is_public)
        if resulting_public and not resulting_approved:
            raise ValidationError("a project cannot be public until it is approved", id=id)

    async def _resolve_initiative_assignment(self, project_id: str, slug: str | None) -> DBRef | None:
        """Validate an initiative assignment and return the link to store (or None to unassign).

        Unassigning needs only project-write access (already enforced downstream). Assigning
        additionally requires that the caller can manage the target initiative and that an
        unapproved target has room under its member cap.
        """
        if slug is None:
            return None

        initiative = await self._initiatives.read_one({"slug": slug})
        if initiative is None or initiative.id is None:
            raise NotFoundError("Initiative not found or not visible", slug=slug)

        self._user.require_manage(*INITIATIVE_PATH, slug, doc_owner=initiative.owner)

        if not initiative.is_approved:
            # Unscoped integrity count: the member cap must see every project assigned to the
            # initiative, even ones the caller cannot. Excluding ``project_id`` keeps re-assigning an
            # already-assigned project idempotent so it never trips the limit.
            members_query: dict[str, Any] = {"initiative.$id": initiative.id}
            if project_id is not None:
                members_query["_id"] = {"$ne": project_id}
            members = await self._projects.count_matching(members_query, scoped=False)
            if members >= self._initiative_limits.max_projects_per_unapproved:
                raise ConflictError(
                    message="unapproved initiative already has the maximum number of assigned projects",
                    slug=slug,
                    limit=self._initiative_limits.max_projects_per_unapproved,
                )

        return DBRef("initiatives", initiative.id)
