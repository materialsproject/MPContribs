from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi_filter import FilterDepends
from starlette.status import HTTP_204_NO_CONTENT

from mpcontribs_api.domains.projects.dependencies import ProjectDep
from mpcontribs_api.domains.projects.models import (
    ProjectFilter,
    ProjectIn,
    ProjectOut,
    ProjectPatch,
)
from mpcontribs_api.pagination import CursorParams

router = APIRouter()


# Brendan TODO: Add in option to select ProjectSummary or ProjectOut
@router.get("", response_model=None)
async def get_project(
    repo: ProjectDep,
    pagination: Annotated[CursorParams, Depends()],
    filter: ProjectFilter = FilterDepends(ProjectFilter),
    fields: Annotated[str | None, Query(alias="_fields")] = None,
):
    """Return paginated projects matching a filter.

    Args:
        repo (ProjectDep): the project repo we depend on
        pagination (CursorParams): arguments for cursor-based pagination
        fields (str | None): optional fields to include in return. If None supplied, all fields are returned

    Returns:
        list[ProjectSummary]: a list of smaller project payloads
    """
    selected = ProjectOut.parse_fields(fields)
    return await repo.get_project(filter=filter, pagination=pagination, fields=selected)


@router.get("/{id}", response_model=ProjectOut)
async def get_project_by_id(
    id: str,
    repo: ProjectDep,
    fields: Annotated[str | None, Query(alias="_fields")] = None,
):
    """Gets a single project by its ID.

    Args:
        id (str): the id of the project to retrieve
        repo (ProjectDep): the project repo we depend on
        fields (str | None): optional fields to include in return. If None supplied, all fields are returned

    Returns:
        ProjectOut: the requested project, actual data returned is determined by the view the user requested
    """
    selected = ProjectOut.parse_fields(fields)
    return await repo.get_project_by_id(id=id, fields=selected)


@router.put("/{id}", response_model=ProjectOut)
async def upsert_project(
    repo: ProjectDep,
    id: str,
    project: ProjectIn,
):
    """Upsert a project by provided id.

    Upsert: Update document if id is found, otherwise insert new document using id.
    Note: Relies on the path param 'id' for finding, rather than the body's id.

    Args:
        repo (ProjectDep): the project repo we depend on
        id (str): the id of the project to retrieve
        project (ProjectIn): the data of the project to upsert

    Returns:
        ProjectOut: the full document that either replaced an old one or was inserted
    """
    return await repo.upsert_project(id=id, data=project)


@router.patch("/{id}", response_model=ProjectOut)
async def patch_project(
    repo: ProjectDep,
    id: str,
    update: ProjectPatch,
):
    """Partial update to project identified with 'id'.

    Note: overwrites fields with given values - arrays are not appended to.

    Args:
        repo (ProjectDep): the project repo we depend on
        id (str): the id of the project to update
        update (ProjectPatch): the partial update to apply - unset fields are dropped
            - Note: If fields are intentionally set to None, None is applied to the field.

    Returns:
        ProjectOut: the full Project with updates applied
    """
    return await repo.patch_project(id=id, update=update)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    repo: ProjectDep,
    id: str,
):
    """Deletes a project matching id.

    Args:
        repo (ProjectDep): the project repo we depend on
        id (str): the id of the project to be deleted
    Returns:
        Response: a response with the 204 response code (rather than FastAPIs default 200)
    """
    await repo.delete_project(id=id)
    return Response(status_code=HTTP_204_NO_CONTENT)
