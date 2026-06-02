from typing import Any, TypeVar, runtime_checkable

from beanie import UpdateResponse
from beanie.operators import Set
from pydantic import BaseModel

from src.mpcontribs_api.auth import User
from src.mpcontribs_api.domains.projects.models import (
    Project,
    ProjectFilter,
    ProjectIn,
    ProjectOut,
    ProjectPatch,
)
from src.mpcontribs_api.exceptions import NotFoundError
from src.mpcontribs_api.pagination import (
    CursorParams,
    Page,
    decode_cursor,
    encode_cursor,
)


# Type checking to get around pyright issues
@runtime_checkable
class HasId(BaseModel):
    id: str


V = TypeVar("V", bound=HasId)
M = TypeVar("M", bound=BaseModel)


class MongoDbProjectRepository:
    def __init__(self, user: User) -> None:
        self._scope = self._build_scope(user)

    @staticmethod
    def _build_scope(user: User) -> dict[str, Any]:
        if user.is_admin:
            return {}
        ors: list[dict[str, Any]] = [{"is_public": True, "is_approved": True}]
        if not user.is_anonymous:
            ors.append({"owner": user.username})
            if user.groups:
                ors.append({"_id": {"$in": sorted(user.groups)}})
        return {"$or": ors}

    def _scoped(self, *clauses: Any) -> dict[str, Any]:
        parts = [c for c in (self._scope, *clauses) if c]
        if not parts:
            return {}
        return parts[0] if len(parts) == 1 else {"$and": parts}

    async def get_project_by_id(self, id: str, *, view: type[M] | None = None):
        # TODO: Verify that self._scope and Project.id == id get combined properly
        return await Project.find_one(
            self._scope, Project.id == id, projection_model=view
        )

    # Brendan TODO: Does not handle compound pagination/sorting (can only paginate on _id, so passing sort arguments does nothing)
    async def get_project(
        self,
        filter: ProjectFilter,
        pagination: CursorParams,
        *,
        view: type[V] | None = None,
    ) -> Page[V | ProjectOut]:
        """Query the Project collection using filtering.

        Only considers the Projects that the User has access to.

        Args:
            filter (ProjectFilter): the query to filter the collection by
            pagination (CursorParams): parameters for pagination using a cursor
            view (type[M]): The type of resposne we should return within the Page
        """
        model = view or ProjectOut

        # Filter projects to just the ones within the user scope
        query = filter.filter(Project.find(self._scope))
        # If cursor was provided
        if pagination.cursor is not None:
            query = query.find(
                Project.id > decode_cursor(pagination.cursor)
            )  # seek past last-seen

        # Get Projects sorted by id (for pagination), project to requested model
        docs = await (
            query.sort(Project.id)
            .limit(pagination.limit + 1)  # +1 probe to detect if there is a next page
            .project(model)
            .to_list()
        )

        # Check if we have more docs, return a Page containing just the number of docs requested and the encoded id for the next cursor
        has_more = len(docs) > pagination.limit
        items = docs[: pagination.limit]
        next_cursor = encode_cursor(str(items[-1].id)) if has_more and items else None
        return Page(items=items, next_cursor=next_cursor)

    async def insert_project(self, project: ProjectIn) -> ProjectOut:
        full_project = Project.from_project_in(project)
        await full_project.insert()
        return ProjectOut.model_validate(full_project)

    async def patch_project(self, id: str, update: ProjectPatch) -> ProjectOut:
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
            existing = await Project.get(Project.id == id)
            if existing is None:
                raise NotFoundError(f"Project with id {id} not found")
            return ProjectOut.model_validate(existing, from_attributes=True)

        # Otherwise, update the fields fully (set)
        # Brendan TODO: Set will replace an entire field
        # - if we want to append to a list (ie. add a reference) we ned Push/AddToSet
        updated = Project.find_one(Project.id == id).update(
            Set(update_data),
            response_type=UpdateResponse.NEW_DOCUMENT,
        )
        if updated is None:
            raise NotFoundError(f"Project with id {id} not found")
        return ProjectOut.model_validate(updated, from_attributes=True)

    async def delete_project(self, id: str):
        """Delete project by id.

        Args:
            id (str): the id of the project to delete
        """
        await Project.find_one(Project.id == id).delete()
