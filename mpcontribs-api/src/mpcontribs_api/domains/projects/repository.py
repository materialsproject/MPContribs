from typing import Any

from mpcontribs_api.authz import User
from mpcontribs_api.domains._shared.repository import MongoDbRepository
from mpcontribs_api.domains.projects.models import (
    Project,
    ProjectFilter,
    ProjectIn,
    ProjectOut,
    ProjectPatch,
)
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

    async def get_project_by_id(self, id: str, fields: frozenset[str] | None):
        """Find a single project by id, scoped to the current user. See ``get_by_id``."""
        return await self.get_by_id(id, fields)

    async def insert_project(self, project: ProjectIn) -> Project:
        """Insert a new project, rejecting a duplicate id. See ``insert_one``."""
        return await self.insert_one(project)

    async def patch_project_by_id(self, id: str, update: ProjectPatch) -> Project:
        """Partially update a project by id, scoped to the current user. See ``patch``."""
        return await self.patch(id, update)

    async def delete_project_by_id(self, id: str) -> None:
        """Delete a project by id, scoped to the current user. See ``delete_by_id``."""
        await self.delete_by_id(id)

    async def upsert_project_by_id(self, id: str, data: ProjectIn) -> Project:
        """Upsert a project by provided id.

        Upsert: Update document if id is found, otherwise insert new document using id.
        Note: Relies on the path param 'id' for finding, rather than the body's id.

        Args:
            id (str): the id of the project to upsert
            data (ProjectIn): the data of the project to upsert

        Returns:
            Project: the full document that either replaced an old one or was inserted
        """
        project = self.document_model.from_input_model(data)
        project.id = id
        return await project.save()
