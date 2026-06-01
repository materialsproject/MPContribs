from typing import Annotated

from fastapi import APIRouter, Query
from fastapi_filter import FilterDepends

from src.mpcontribs_api.domains.projects.dependencies import ProjectDep
from src.mpcontribs_api.domains.projects.models import (
    _VIEW_MODELS,
    ProjectFilter,
    ProjectResponse,
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


@router.get("/{id}", response_model=ProjectResponse | ProjectSummary)
async def get_project_by_id(
    id: str,
    repo: ProjectDep,
    *,
    view: ProjectView = ProjectView.full,
):
    return await repo.get_project_by_id(id=id, view=_VIEW_MODELS[view])


@router.post("", response_model=ProjectResponse)
async def post_project(
    repo: ProjectDep,
    project: ProjectPost = Depends(authorize_resource),
):
    return await repo.post(project=project)
