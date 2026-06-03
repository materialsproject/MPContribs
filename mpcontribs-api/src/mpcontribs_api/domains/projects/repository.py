from typing import Any, TypeVar

from beanie import UpdateResponse
from beanie.operators import Set
from pydantic import BaseModel

from src.mpcontribs_api.auth import User
from src.mpcontribs_api.domains._shared.repository import MongoDbRepository
from src.mpcontribs_api.domains.projects.models import (
    Project,
    ProjectFilter,
    ProjectIn,
    ProjectOut,
    ProjectPatch,
)
from src.mpcontribs_api.exceptions import ConflictError, NotFoundError
from src.mpcontribs_api.pagination import (
    CursorParams,
)


# Type checking to get around pyright issues
class HasId(BaseModel):
    id: str


V = TypeVar("V", bound=HasId)
M = TypeVar("M", bound=BaseModel)


class MongoDbProjectRepository(MongoDbRepository[Project, ProjectIn, ProjectOut]):
    """A repository layer for access to MongoDB.

    This is the layer that directly interacts with database operations

    Attributes:
        _scope (dict[str, Any]): additional terms to inject into mongo queries to enforce user authorization on
            resources
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

    # Brendan TODO: figure out return type
    async def get_project_by_id(self, id: str, fields: frozenset[str] | None):
        """Finds a single project by ID.

        Args:
            id (str): the id of the project to find
            fields (frozenset[str] | None): a BaseModel to use for projection. If none, the document is returned without
                projection

        Returns:
            ProjectOut: a projection of ProjectOut containing 'fields' from requested id
        """
        # TODO: Verify that self._scope and Project.id == id get combined properly
        return await self.document_model.find_one(
            self._scope,
            self.document_model.id == id,
            projection_model=self.out_model.projection(fields),
        )

    # Brendan TODO: Does not handle compound pagination/sorting
    #   can only paginate on _id, so passing sort arguments does nothing
    async def get_project(
        self,
        filter: ProjectFilter,
        pagination: CursorParams,
        fields: frozenset[str] | None,
    ):
        """Query the Project collection using filtering.

        Only considers the Projects that the User has access to.

        Args:
            filter (ProjectFilter): the query to filter the collection by
            pagination (CursorParams): parameters for pagination using a cursor
            fields (frozenset[str] | None): the fields to use for projection. If none, the document is returned without
                projection
        """
        return await self.get_many(pagination=pagination, filter=filter, fields=fields)

    async def insert_project(self, project: ProjectIn) -> Project:
        """Inserst a new project.

        Args:
            project (ProjectIn): the project to be inserted

        Returns:
            Project: the project after succesful insertion
        """
        id_exists = await self.document_model.find_one(self.document_model.id == project.id)
        # Brendan TODO:
        if id_exists:
            raise ConflictError(f"Cannot insert project.\n Project with ID {project.id} exists")
        full_project = self.document_model.from_input_model(project)
        await full_project.insert()
        return full_project

    async def patch_project(self, id: str, update: ProjectPatch) -> Project:
        """Partial update to project identified with 'id'.

        Note: overwrites fields with given values - arrays are not appended to.

        Args:
            id (str): the id of the project to update
            update (ProjectPatch): the partial update to apply - unset fields are dropped
                - Note: If fields are intentionally set to None, None is applied to the field.

        Returns:
            The Project with updates applied
        """
        # Only retain set fields (patch)
        update_data = update.model_dump(exclude_unset=True)
        # If update is empty, return the model anyways (consistent behavior)
        if not update_data:
            existing = await self.document_model.get(id)
            if existing is None:
                raise NotFoundError(f"Project with id {id} not found")
            return existing

        # Otherwise, update the fields fully (set)
        # Brendan TODO: Set will replace an entire field
        # - if we want to append to a list (ie. add a reference) we ned Push/AddToSet
        query = self.document_model.find_one(self.document_model.id == id).update(
            Set(update_data),
            response_type=UpdateResponse.NEW_DOCUMENT,
        )
        updated = await query  # pyright: ignore[reportGeneralTypeIssues] # beanie UpdateQuery is awaitable, but pyright doesn't see it
        if updated is None:
            raise NotFoundError(f"Project with id {id} not found")
        return updated

    async def delete_project(self, id: str):
        """Delete project by id.

        Args:
            id (str): the id of the project to delete
        """
        await self.document_model.find_one(self.document_model.id == id).delete()

    async def upsert_project(self, id: str, data: ProjectIn) -> Project:
        """Upsert a project by provided id.

        Upsert: Update document if id is found, otherwise insert new document using id.
        Note: Relies on the path param 'id' for finding, rather than the body's id.

        Args:
            repo (ProjectDep): the project repo we depend on
            id (str): the id of the project to retrieve
            project (ProjectIn): the data of the project to upsert

        Returns:
            Project: the full document that either replaced an old one or was inserted
        """
        project = self.document_model.from_input_model(data)
        project.id = id
        return await project.save()
