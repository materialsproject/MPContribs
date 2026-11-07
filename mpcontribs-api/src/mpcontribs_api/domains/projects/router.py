from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi_filter import FilterDepends

from mpcontribs_api.domains._shared.types import FieldSelector
from mpcontribs_api.domains.projects.dependencies import ProjectServiceDep
from mpcontribs_api.domains.projects.models import (
    ProjectFilter,
    ProjectOut,
)
from mpcontribs_api.pagination import CursorParams, Page

# Projects are worker-written documents: these endpoints are read-only. Creation, replacement,
# and deletion all flow through the /uploads endpoints.
router = APIRouter()


@router.get("", response_model_exclude_unset=True)
async def read_many(
    service: ProjectServiceDep,
    pagination: Annotated[CursorParams, Depends()],
    filter: ProjectFilter = FilterDepends(ProjectFilter),
    fields: FieldSelector = None,
) -> Page[ProjectOut]:
    """Return paginated projects matching a filter.

    Args:
        service (ProjectServiceDep): the project service we depend on
        pagination (CursorParams): arguments for cursor-based pagination
        fields (list[str] | None): optional ``_fields`` selection. Omitted -> server defaults;
            empty (``?_fields=``) -> identity fields only; ``_all`` -> the full document

    Returns:
        list[ProjectSummary]: a list of smaller project payloads
    """
    selected = ProjectOut.parse_fields(fields)
    return await service.read_many(filter=filter, pagination=pagination, fields=selected)


@router.get("/search", response_model_exclude_unset=True)
async def search(
    service: ProjectServiceDep,
    query: str,
    limit: int = 10,
) -> list[ProjectOut]:
    """Full-text search across projects.

    Declared before ``/{id}`` so the literal ``search`` segment is never captured as a project id.

    Args:
        service (ProjectServiceDep): the project service we depend on
        query (str): the free-text search string

    Returns:
        list[ProjectOut]: the matching projects
    """
    return await service.search(query=query, limit=limit)


@router.get("/{id}", response_model_exclude_unset=True)
async def read_one(
    id: str,
    service: ProjectServiceDep,
    fields: FieldSelector = None,
) -> ProjectOut | None:
    """Gets a single project by its ID, or None when no in-scope project matches.

    Args:
        id (str): the id of the project to retrieve
        service (ProjectServiceDep): the project service we depend on
        fields (list[str] | None): optional ``_fields`` selection. Omitted -> server defaults;
            empty (``?_fields=``) -> identity fields only; ``_all`` -> the full document

    Returns:
        ProjectOut: the requested project, actual data returned is determined by the view the user requested
    """
    selected = ProjectOut.parse_fields(fields)
    return await service.read_one({"id": id}, fields=selected)
