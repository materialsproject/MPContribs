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


@router.get("", response_model=list[ProjectSummary])
async def get_project(
    repo: ProjectDep,
    pagination: Annotated[CursorParams, Query()],
    filter: ProjectFilter = FilterDepends(ProjectFilter),
):
    return await repo.get_project(filter=filter, pagination=pagination)


@router.get("/{id}", response_model=ProjectOut | ProjectSummary)
async def get_project_by_id(
    id: str,
    repo: ProjectDep,
    *,
    view: ProjectView = ProjectView.full,
):
    return await repo.get_project_by_id(id=id, view=_VIEW_MODELS[view])


@router.post("", response_model=ProjectOut)
async def insert_project(
    repo: ProjectDep,
    project: ProjectIn,
):
    return await repo.insert_project(project=project)


@router.patch("{id}", response_model=ProjectOut)
async def patch_project(
    repo: ProjectDep,
    id: str,
    update: ProjectPatch,
):
    """Partial update to project identified with 'id'.

    Note: overwrites fields with given values - arrays are not appended to.

    Args:
        id (str): the id of the project to update
        update (ProjectPatch): the partial update to apply - unset fields are dropped
            - Note: If fields are intentionally set to None, None is applied to the field.

    Returns:
        The Project with updates applied
    """
    return await repo.patch_project(id=id, update=update)


@router.delete("{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    repo: ProjectDep,
    id: str,
):
    await repo.delete_project(id=id)
    return Response(status_code=HTTP_204_NO_CONTENT)
