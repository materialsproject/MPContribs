from typing import Annotated

from fastapi import APIRouter, Query, Response, status
from fastapi_filter import FilterDepends
from starlette.status import HTTP_204_NO_CONTENT

from src.mpcontribs_api.domains.projects.dependencies import ProjectDep
from src.mpcontribs_api.domains.projects.models import (
    _VIEW_MODELS,
    ProjectFilter,
    ProjectIn,
    ProjectOut,
    ProjectPatch,
    ProjectSummary,
    ProjectView,
)
from src.mpcontribs_api.pagination import CursorParams

router = APIRouter()


# Brendan TODO: Add in option to select ProjectSummary or ProjectOut
@router.get("", response_model=list[ProjectSummary])
async def get_project(
    repo: ProjectDep,
    pagination: Annotated[CursorParams, Query()],
    filter: ProjectFilter = FilterDepends(ProjectFilter),
):
    """Return paginated projects matching a filter.

    Args:
        repo (ProjectDep): the project repo we depend on
        pagination (CursorParams): arguments for cursor-based pagination
        filter (ProjectFilter): arguments for filtering projects

    Returns:
        list[ProjectSummary]: a list of smaller project payloads"""
    return await repo.get_project(filter=filter, pagination=pagination)


@router.get("/{id}", response_model=ProjectOut | ProjectSummary)
async def get_project_by_id(
    id: str,
    repo: ProjectDep,
    view: ProjectView = ProjectView.full,
):
    """Gets a single project by its ID.

    Args:
        id (str): the id of the project to retrieve
        repo (ProjectDep): the project repo we depend on
        view (ProjectView): user selection for which type of return is desired (smaller summary or the complete project)

    Returns:
        ProjectOut | ProjectSummary: the requested project, actual data returned is determined by the view the user requested
    """
    return await repo.get_project_by_id(id=id, view=_VIEW_MODELS[view])


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
