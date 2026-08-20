from typing import Any

from mpcontribs_api.authz import User
from mpcontribs_api.config import get_settings
from mpcontribs_api.domains._shared.models import DeleteResponse
from mpcontribs_api.domains.initiatives.models import (
    Initiative,
    InitiativeFilter,
    InitiativeIn,
    InitiativeOut,
    InitiativePatch,
)
from mpcontribs_api.domains.initiatives.repository import MongoDbInitiativeRepository
from mpcontribs_api.domains.projects.repository import MongoDbProjectRepository
from mpcontribs_api.exceptions import ConflictError, NotFoundError, PermissionError, ValidationError
from mpcontribs_api.pagination import CursorParams, Page


class InitiativeService:
    """Owns initiative write policy; the repository is a scoped query/persistence toolbox.

    Every authorization decision, invariant, and quota for initiatives lives here:

    - **Authentication** on insert.
    - **Per-owner unapproved quota** — a non-admin may not exceed ``max_unapproved_per_owner``.
    - **Manage rights** on patch — the caller must own the initiative or hold its ``initiative:<slug>``
      role (or be an admin).
    - **Admin-only approval** — only an admin may set ``is_approved``.
    - **Owner-or-admin delete** — collaborators may contribute projects but not dissolve the effort;
      a caller who cannot see the initiative gets a 404, one who can see but does not own it gets a 403.
    - **The ``public ⇒ approved`` invariant**, re-checked on patch because a partial ``$set`` bypasses
      the document validator.
    """

    def __init__(
        self, user: User, initiatives: MongoDbInitiativeRepository, projects: MongoDbProjectRepository
    ) -> None:
        self._user = user
        self._initiatives = initiatives
        self._projects = projects
        self._limits = get_settings().domain.initiatives

    async def get_many(
        self, pagination: CursorParams, filter: InitiativeFilter, fields: frozenset[str] | None
    ) -> Page[InitiativeOut]:
        """Return a page of scoped initiatives matching ``filter``."""
        return await self._initiatives.get_many(pagination=pagination, filter=filter, fields=fields)

    async def get_one(
        self, identifiers: dict[str, Any], fields: frozenset[str] | None
    ) -> Initiative | InitiativeOut | None:
        """Return the single scoped initiative matching ``identifiers`` (``{"slug": ...}``)."""
        return await self._initiatives.get_one(identifiers, fields)

    async def insert_one(self, data: InitiativeIn) -> Initiative:
        """Create an initiative owned by the caller, enforcing the per-owner unapproved quota.

        ``owner`` is forced to the caller and the initiative starts unapproved and private. A
        non-admin who already owns ``max_unapproved_per_owner`` unapproved initiatives is rejected
        with 409; a duplicate ``slug`` is also a 409 (raised by the repository).
        """
        # The route enforces authentication, so an anonymous caller should never reach here.
        if self._user.username is None:
            raise PermissionError(required_role="authenticated")

        if not self._user.is_admin:
            # Unscoped: the per-owner unapproved cap counts every one of the owner's unapproved
            # initiatives, regardless of what the current caller can see.
            unapproved = await self._initiatives.count_matching(
                {"owner": self._user.username, "is_approved": False}, scoped=False
            )
            if unapproved >= self._limits.max_unapproved_per_owner:
                raise ConflictError(
                    "owner already has the maximum number of unapproved initiatives",
                    limit=self._limits.max_unapproved_per_owner,
                )

        # The repository translates the unique-slug DuplicateKeyError into a ConflictError whose
        # context carries the slug (Initiative.identifier_fields() == {"slug"}).
        initiative = self._initiatives.document_model.from_input_model(data, owner=self._user.username)
        return await self._initiatives.insert_one(initiative)

    async def patch_one(self, identifiers: dict[str, Any], update: InitiativePatch) -> Initiative:
        """Patch a scoped initiative by ``slug``, enforcing manage rights and approval rules.

        - The caller must be able to *manage* the initiative (owner/collaborator/admin).
        - Only an admin may change ``is_approved``.
        - The resulting state must satisfy ``is_public ⇒ is_approved`` (re-checked here because a
          partial ``$set`` does not run the document validator).
        """
        slug = identifiers["slug"]
        existing = await self._initiatives.get_one(identifiers)
        if existing is None:
            raise NotFoundError("Initiative not found", slug=slug)
        if not (self._user.can_manage(id=slug, resource="initiative") or self._user.username == existing.owner):
            raise PermissionError(required_role="initiative-owner-collaborator-or-admin")

        data = update.model_dump(exclude_unset=True)
        if "is_approved" in data and not self._user.is_admin:
            raise PermissionError("only admins can set `is_approved`", required_role="admin")

        resulting_approved = data.get("is_approved", existing.is_approved)
        resulting_public = data.get("is_public", existing.is_public)
        if resulting_public and not resulting_approved:
            raise ValidationError("an initiative cannot be public until it is approved", slug=slug)

        return await self._initiatives.patch_one(identifiers, update)

    async def delete_one(self, identifiers: dict[str, Any]) -> DeleteResponse:
        """Delete a scoped initiative by ``slug``. Restricted to the owner or an admin.

        Collaborators may contribute projects but may not delete. A caller who cannot
        see the initiative gets a 404; one who can see it but does not own it gets a 403. After the
        initiative is removed, the ``initiative`` link is unset on every member project.
        """
        existing = await self._initiatives.get_one(identifiers)
        if existing is None:
            raise NotFoundError("Initiative not found", **identifiers)
        if not (self._user.is_admin or existing.owner == self._user.username):
            raise PermissionError(required_role="owner-or-admin")
        response = await self._initiatives.delete_one(identifiers)
        if existing.id is not None:
            await self._projects.clear_initiative_refs(existing.id)
        return response
