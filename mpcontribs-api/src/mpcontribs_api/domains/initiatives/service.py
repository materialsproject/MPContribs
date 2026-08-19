from typing import Any

from mpcontribs_api.domains._shared.models import DeleteResponse
from mpcontribs_api.domains.initiatives.models import (
    Initiative,
    InitiativeFilter,
    InitiativeIn,
    InitiativeOut,
    InitiativePatch,
)
from mpcontribs_api.domains.initiatives.repository import InitiativeRepository
from mpcontribs_api.pagination import CursorParams, Page


class InitiativeService:
    """Service layer for initiatives.

    Initiatives have no cross-domain coordination, so the service is a thin pass-through that owns
    ``_fields`` parsing and keeps the router off the repository.
    """

    def __init__(self, initiatives: InitiativeRepository) -> None:
        self._initiatives = initiatives

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
        """Create an initiative owned by the caller. See repository ``insert_one``."""
        return await self._initiatives.insert_one(data=data)

    async def patch_one(self, identifiers: dict[str, Any], update: InitiativePatch) -> Initiative:
        """Patch the scoped initiative matching ``identifiers`` (``{"slug": ...}``). See repository."""
        return await self._initiatives.patch_one(identifiers, update=update)

    async def delete_one(self, identifiers: dict[str, Any]) -> DeleteResponse:
        """Delete the scoped initiative matching ``identifiers`` (``{"slug": ...}``). See repository."""
        return await self._initiatives.delete_one(identifiers)
