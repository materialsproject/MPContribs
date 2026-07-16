from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from fastapi_filter import FilterDepends

from mpcontribs_api.dependencies import require_user
from mpcontribs_api.domains._shared.bulk import BulkWriteSummary
from mpcontribs_api.domains._shared.models import DeleteResponse
from mpcontribs_api.domains._shared.types import FieldSelector, PrefixedEmail, SearchStr
from mpcontribs_api.domains.project_groups.dependencies import ProjectGroupDep, ProjectGroupServiceDep
from mpcontribs_api.domains.project_groups.models import (
    ProjectGroupFilter,
    ProjectGroupIn,
    ProjectGroupOut,
    ProjectGroupPatch,
    ProjectRefs,
)
from mpcontribs_api.pagination import CursorParams

router = APIRouter()


@router.get("")
async def get_project_groups(
    repo: ProjectGroupDep,
    pagination: Annotated[CursorParams, Depends()],
    filter: ProjectGroupFilter = FilterDepends(ProjectGroupFilter),
    fields: FieldSelector = ProjectGroupOut.default_fields(),
):
    """Return paginated project groups matching a filter.

    Args:
        repo (ProjectGroupDep): the project group repo we depend on
        pagination (CursorParams): arguments for cursor-based pagination
        filter (ProjectGroupFilter): optional filters to select ProjectGroups
        fields (FieldSelector): the fields to return to a user
    """
    selected = ProjectGroupOut.parse_fields(fields)
    return await repo.get_project_groups(pagination=pagination, filter=filter, fields=selected)


@router.get("/item")
async def get_project_group(
    repo: ProjectGroupDep,
    name: SearchStr,
    owner: PrefixedEmail,
    fields: FieldSelector = ProjectGroupOut.default_fields(),
):
    """Return the single project group identified by ``name`` + ``owner``.

    Args:
        repo (ProjectGroupDep): the project group repo we depend on
        name (SearchStr): the project group's name
        owner (PrefixedEmail): the project group's owner
        fields (FieldSelector): the fields to return to a user
    """
    selected = ProjectGroupOut.parse_fields(fields)
    return await repo.get_project_group(name=name, owner=owner, fields=selected)


@router.post("", response_model=ProjectGroupOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_user)])
async def insert_project_group(
    repo: ProjectGroupDep,
    project_group: ProjectGroupIn,
):
    """Insert a new project group.

    Args:
        repo (ProjectGroupDep): the project group repo we depend on
        project_group (ProjectGroupIn): the project group to insert
    """
    return await repo.insert_project_group(project_group=project_group)


@router.patch("/item", response_model=ProjectGroupOut, dependencies=[Depends(require_user)])
async def patch_project_group(
    repo: ProjectGroupDep,
    name: SearchStr,
    owner: PrefixedEmail,
    update: ProjectGroupPatch,
):
    """Partially update the project group identified by ``name`` + ``owner``.

    Args:
        repo (ProjectGroupDep): the project group repo we depend on
        name (SearchStr): the project group's name
        owner (PrefixedEmail): the project group's owner
        update (ProjectGroupPatch): the partial update to apply - unset fields are dropped
    """
    return await repo.patch_project_group(name=name, owner=owner, update=update)


@router.delete("/item", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_user)])
async def delete_project_group(
    repo: ProjectGroupDep,
    name: SearchStr,
    owner: PrefixedEmail,
):
    """Delete the single project group identified by ``name`` + ``owner``.

    Raises 404 if no such group is visible to the caller, 409 if the identifiers are ambiguous.

    Args:
        repo (ProjectGroupDep): the project group repo we depend on
        name (SearchStr): the project group's name
        owner (PrefixedEmail): the project group's owner
    """
    await repo.delete_project_group(name=name, owner=owner)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("", response_model=DeleteResponse, dependencies=[Depends(require_user)])
async def delete_project_groups(
    repo: ProjectGroupDep,
    filter: ProjectGroupFilter = FilterDepends(ProjectGroupFilter),
):
    """Bulk-delete every project group matching ``filter`` (e.g. all with a given owner).

    Args:
        repo (ProjectGroupDep): the project group repo we depend on
        filter (ProjectGroupFilter): the query selecting which project groups to delete
    """
    return await repo.delete_project_groups(filter=filter)


@router.post("/item/projects", response_model=BulkWriteSummary[str], dependencies=[Depends(require_user)])
async def add_projects_by_identifiers(
    service: ProjectGroupServiceDep,
    name: SearchStr,
    owner: PrefixedEmail,
    body: ProjectRefs,
):
    """Add projects to the group identified by ``name`` + ``owner``.

    Each project is verified against the projects collection (scoped to the caller); unknown or
    invisible projects are reported per-item in the response rather than failing the whole request.
    """
    return await service.add_projects_by_identifiers(name=name, owner=owner, project_ids=body.project_ids)


@router.delete("/item/projects", response_model=BulkWriteSummary[str], dependencies=[Depends(require_user)])
async def delete_projects_by_identifiers(
    service: ProjectGroupServiceDep,
    name: SearchStr,
    owner: PrefixedEmail,
    body: ProjectRefs,
):
    """Delete projects from the group identified by ``name`` + ``owner``.

    Ids that are not members of the group are reported per-item in the response.
    """
    return await service.delete_projects_by_identifiers(name=name, owner=owner, project_ids=body.project_ids)


@router.post("/{id}/projects", response_model=BulkWriteSummary[str], dependencies=[Depends(require_user)])
async def add_projects_by_id(
    service: ProjectGroupServiceDep,
    id: str,
    body: ProjectRefs,
):
    """Add projects to the group identified by ``id``. See ``add_projects_by_identifiers``."""
    return await service.add_projects_by_id(group_id=id, project_ids=body.project_ids)


@router.delete("/{id}/projects", response_model=BulkWriteSummary[str], dependencies=[Depends(require_user)])
async def delete_projects_by_id(
    service: ProjectGroupServiceDep,
    id: str,
    body: ProjectRefs,
):
    """Delete projects from the group identified by ``id``. See ``delete_projects_by_identifiers``."""
    return await service.delete_projects_by_id(group_id=id, project_ids=body.project_ids)
