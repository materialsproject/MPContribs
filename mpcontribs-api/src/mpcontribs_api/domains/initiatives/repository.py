from typing import Any

from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import DuplicateKeyError

from mpcontribs_api.authz import User
from mpcontribs_api.config import get_settings
from mpcontribs_api.domains._shared.models import DeleteResponse
from mpcontribs_api.domains._shared.repository import MongoDbRepository
from mpcontribs_api.domains.initiatives.models import (
    Initiative,
    InitiativeFilter,
    InitiativeIn,
    InitiativeOut,
    InitiativePatch,
)
from mpcontribs_api.exceptions import ConflictError, NotFoundError, PermissionError, ValidationError
from mpcontribs_api.pagination import CursorParams, Page


class InitiativeRepository(
    MongoDbRepository[Initiative, InitiativeIn, InitiativeOut, InitiativeFilter, InitiativePatch]
):
    document_model = Initiative
    out_model = InitiativeOut

    def __init__(self, user: User) -> None:
        super().__init__(user)
        self._limits = get_settings().domain.initiatives

    @staticmethod
    def _build_scope(user: User) -> dict[str, Any]:
        """Scope reads to what the caller may see: public+approved, owned, or collaborated-on."""
        if user.is_admin:
            return {}
        ors: list[dict[str, Any]] = [{"is_public": True, "is_approved": True}]
        if not user.is_anonymous:
            ors.append({"owner": user.username})
            slugs = user.initiative_roles
            if slugs:
                ors.append({"slug": {"$in": sorted(slugs)}})
        return {"$or": ors}

    async def get_initiatives(
        self,
        pagination: CursorParams,
        filter: InitiativeFilter,
        fields: frozenset[str] | None,
    ) -> Page[InitiativeOut]:
        """Return a scoped, filtered, paginated page of initiatives. See ``get_many``."""
        return await self.get_many(pagination=pagination, filter=filter, fields=fields)

    async def insert_initiative(self, data: InitiativeIn) -> Initiative:
        """Create an initiative owned by the caller, enforcing the per-owner unapproved quota.

        ``owner`` is forced to the caller and the initiative starts unapproved and private. A
        non-admin who already owns ``max_unapproved_per_owner`` unapproved initiatives is rejected
        with 409. A duplicate ``slug`` (globally unique) is also a 409.
        """
        if self._user.username is None:
            raise PermissionError(required_role="authenticated")

        if not self._user.is_admin:
            unapproved = await self.document_model.find(
                self.document_model.owner == self._user.username,
                self.document_model.is_approved == False,  # noqa: E712 — Beanie needs the value, not `is`
            ).count()
            if unapproved >= self._limits.max_unapproved_per_owner:
                raise ConflictError(
                    "owner already has the maximum number of unapproved initiatives",
                    limit=self._limits.max_unapproved_per_owner,
                )

        initiative = self.document_model.from_input_model(data=data, owner=self._user.username)
        try:
            await initiative.insert()
        except DuplicateKeyError as exc:  # unique slug index
            raise ConflictError("an initiative with this slug already exists", slug=data.slug) from exc
        return initiative

    async def patch_one(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, identifiers: dict[str, Any], update: InitiativePatch, session: AsyncClientSession | None = None
    ) -> Initiative:
        """Patch a scoped initiative by ``slug``, enforcing manage rights and approval rules.

        - The caller must be able to *manage* the initiative (owner/collaborator/admin)
        - Only an admin may change ``is_approved``.
        - The resulting state must satisfy ``is_public ⇒ is_approved`` (re-checked here because a
          partial ``$set`` does not run the document validator).

        ``identifiers`` is the ``{"slug": ...}`` form; the auth checks run against the resolved
        document, and the write itself is delegated to the base :meth:`MongoDbRepository.patch_one`.
        """
        slug = identifiers["slug"]
        existing = await self.document_model.find_one(self._scope, self.document_model.slug == slug)
        if existing is None:
            raise NotFoundError("Initiative not found", slug=slug)
        if not (
            self._user.can_manage(id=existing.slug, resource="initiative") or self._user.username == existing.owner
        ):
            raise PermissionError(required_role="initiative-owner-collaborator-or-admin")

        data = update.model_dump(exclude_unset=True)
        if "is_approved" in data and not self._user.is_admin:
            raise PermissionError("only admins can set `is_approved`", required_role="admin")

        resulting_approved = data.get("is_approved", existing.is_approved)
        resulting_public = data.get("is_public", existing.is_public)
        if resulting_public and not resulting_approved:
            raise ValidationError("an initiative cannot be public until it is approved", slug=slug)

        return await super().patch_one(identifiers, update, session=session)

    async def delete_one(
        self, identifiers: dict[str, Any], session: AsyncClientSession | None = None
    ) -> DeleteResponse:
        """Delete a scoped initiative by ``slug``. Restricted to the owner or an admin.

        Collaborators may contribute projects but may not dissolve the effort. Deleting an
        initiative does not touch member projects; their ``initiative`` link simply dangles until
        re-pointed (reads resolve a missing link to null).

        ``identifiers`` is the ``{"slug": ...}`` form; the write is delegated to the base
        :meth:`MongoDbRepository.delete_one`.
        """
        slug = identifiers["slug"]
        existing = await self.document_model.find_one(self._scope, self.document_model.slug == slug)
        if existing is None:
            raise NotFoundError("Initiative not found", slug=slug)
        if not (self._user.is_admin or existing.owner == self._user.username):
            raise PermissionError(required_role="owner-or-admin")
        return await super().delete_one(identifiers, session=session)
