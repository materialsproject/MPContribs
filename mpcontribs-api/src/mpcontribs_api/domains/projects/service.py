from typing import Any

from mpcontribs_api.domains.projects.models import (
    ProjectFilter,
    ProjectOut,
)
from mpcontribs_api.domains.projects.repository import MongoDbProjectRepository
from mpcontribs_api.exceptions import ValidationError
from mpcontribs_api.pagination import CursorParams, Page


class ProjectService:
    """Read-only access service for projects.

    Projects are worker-written: creation, replacement, and deletion all flow through the
    ``/uploads`` endpoints, so this service exposes reads only (list, fetch, search).
    """

    def __init__(self, projects: MongoDbProjectRepository) -> None:
        self._projects = projects

    async def read_many(
        self, filter: ProjectFilter, pagination: CursorParams, fields: frozenset[str] | None
    ) -> Page[ProjectOut]:
        """Return a page of scoped projects matching ``filter``."""
        return await self._projects.read_many(filter=filter, pagination=pagination, fields=fields)

    async def read_one(self, identifiers: dict[str, Any], fields: frozenset[str] | None) -> ProjectOut | None:
        """Return the single scoped project matching ``identifiers`` (``{"id": ...}``), or None when absent."""
        return await self._projects.read_one(identifiers, fields)

    async def search(self, query: str, limit: int = 10) -> list[ProjectOut]:
        """Full-text search across projects."""
        if not query:
            raise ValidationError(message="search query cannot be empty")
        return await self._projects.search(query=query, limit=limit)
