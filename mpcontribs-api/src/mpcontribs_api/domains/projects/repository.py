from typing import Any, TypeVar, runtime_checkable

from pydantic import BaseModel

from src.mpcontribs_api.auth import User
from src.mpcontribs_api.domains.projects.models import (
    Project,
    ProjectFilter,
    ProjectResponse,
)
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

# class IScopedProjectRepository(Protocol):
#     @overload
#     async def get_project(self, query: dict[str, Any]) -> ProjectResponse | None: ...
#     @overload
#     async def get_project(
#         self, query: dict[str, Any], *, view: type[BaseModel]
#     ) -> BaseModel | None: ...
#     async def get_project(
#         self,
#         query: dict[str, Any],
#         *,
#         view: type[BaseModel] = ProjectResponse,
#     ) -> BaseModel | None: ...

#     @overload
#     async def get_project_by_id(self, id: str) -> ProjectResponse | None: ...
#     @overload
#     async def get_project_by_id(self, id: str, *, view: type[M]) -> M | None: ...
#     async def get_project_by_id(
#         self,
#         id: str,
#         *,
#         view: type[M] | None = None,
#     ) -> M | ProjectResponse | None: ...


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
    ) -> Page[V | ProjectResponse]:
        """Query the Project collection using filtering.

        Only considers the Projects that the User has access to.

        Args:
            filter (ProjectFilter): the query to filter the collection by
            pagination (CursorParams): parameters for pagination using a cursor
            view (type[M]): The type of resposne we should return within the Page
        """
        model = view or ProjectResponse

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
