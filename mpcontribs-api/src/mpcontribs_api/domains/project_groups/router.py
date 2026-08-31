from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from fastapi_filter import FilterDepends

from mpcontribs_api.dependencies import require_user
from mpcontribs_api.domains._shared.bulk import BulkWriteSummary
from mpcontribs_api.domains._shared.models import DeleteResponse
from mpcontribs_api.domains._shared.types import FieldSelector, PrefixedEmail, SearchStr
from mpcontribs_api.domains.project_groups.dependencies import ProjectGroupServiceDep
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
async def read_many(
    service: ProjectGroupServiceDep,
    pagination: Annotated[CursorParams, Depends()],
    filter: ProjectGroupFilter = FilterDepends(ProjectGroupFilter),
    fields: FieldSelector = None,
):
    """Return paginated project groups matching a filter.

    Args:
        service (ProjectGroupServiceDep): the project group service we depend on
        pagination (CursorParams): arguments for cursor-based pagination
        filter (ProjectGroupFilter): optional filters to select ProjectGroups
        fields (FieldSelector): the fields to return to a user
    """
    selected = ProjectGroupOut.parse_fields(fields)
    return await service.read_many(pagination=pagination, filter=filter, fields=selected)


@router.get("/item")
async def read_one(
    service: ProjectGroupServiceDep,
    name: SearchStr,
    owner: PrefixedEmail,
    fields: FieldSelector = None,
):
    """Return the single project group identified by ``name`` + ``owner``.

    Args:
        service (ProjectGroupServiceDep): the project group service we depend on
        name (SearchStr): the project group's name
        owner (PrefixedEmail): the project group's owner
        fields (FieldSelector): the fields to return to a user
    """
    selected = ProjectGroupOut.parse_fields(fields)
    return await service.read_one({"name": name, "owner": owner}, fields=selected)


@router.post(
    "", response_model=ProjectGroupOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_user)]
)
async def insert_one(
    service: ProjectGroupServiceDep,
    project_group: ProjectGroupIn,
):
    """Insert a new project group.

    Each referenced project is verified against the projects collection (scoped to the caller);
    creation is rejected with 404 if any project id is unknown or not visible.

    Args:
        service (ProjectGroupServiceDep): the project group service we depend on
        project_group (ProjectGroupIn): the project group to insert
    """
    return await service.insert_one(project_group=project_group)


@router.patch("/item", response_model=ProjectGroupOut, dependencies=[Depends(require_user)])
async def update_one(
    service: ProjectGroupServiceDep,
    name: SearchStr,
    owner: PrefixedEmail,
    update: ProjectGroupPatch,
):
    """Partially update the project group identified by ``name`` + ``owner``.

    Args:
        service (ProjectGroupServiceDep): the project group service we depend on
        name (SearchStr): the project group's name
        owner (PrefixedEmail): the project group's owner
        update (ProjectGroupPatch): the partial update to apply - unset fields are dropped
    """
    return await service.update_one({"name": name, "owner": owner}, update=update)


@router.delete("/item", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_user)])
async def delete_one(
    service: ProjectGroupServiceDep,
    name: SearchStr,
    owner: PrefixedEmail,
):
    """Delete the single project group identified by ``name`` + ``owner``.

    Raises 404 if no such group is visible to the caller, 409 if the identifiers are ambiguous.

    Args:
        service (ProjectGroupServiceDep): the project group service we depend on
        name (SearchStr): the project group's name
        owner (PrefixedEmail): the project group's owner
    """
    await service.delete_one({"name": name, "owner": owner})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("", response_model=DeleteResponse, dependencies=[Depends(require_user)])
async def delete_many(
    service: ProjectGroupServiceDep,
    filter: ProjectGroupFilter = FilterDepends(ProjectGroupFilter),
):
    """Bulk-delete every project group matching ``filter`` (e.g. all with a given owner).

    Args:
        service (ProjectGroupServiceDep): the project group service we depend on
        filter (ProjectGroupFilter): the query selecting which project groups to delete
    """
    return await service.delete_many(filter=filter)


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
    return await service.add_projects({"name": name, "owner": owner}, body.project_ids)


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
    return await service.delete_projects({"name": name, "owner": owner}, body.project_ids)


@router.post("/{id}/projects", response_model=BulkWriteSummary[str], dependencies=[Depends(require_user)])
async def add_projects_by_id(
    service: ProjectGroupServiceDep,
    id: str,
    body: ProjectRefs,
):
    """Add projects to the group identified by ``id``. See ``add_projects``."""
    return await service.add_projects({"id": id}, body.project_ids)


@router.delete("/{id}/projects", response_model=BulkWriteSummary[str], dependencies=[Depends(require_user)])
async def delete_projects_by_id(
    service: ProjectGroupServiceDep,
    id: str,
    body: ProjectRefs,
):
    """Delete projects from the group identified by ``id``. See ``delete_projects``."""
    return await service.delete_projects({"id": id}, body.project_ids)


# Primary-key CRUD, symmetric to the ``/item`` (name+owner) routes above. Declared after ``/item`` so
# the literal path is never captured as an ``{id}``.
@router.get("/{id}")
async def read_one_by_identity(
    service: ProjectGroupServiceDep,
    id: str,
    fields: FieldSelector = None,
):
    """Return the single project group identified by its ``_id``."""
    selected = ProjectGroupOut.parse_fields(fields)
    return await service.read_one({"id": id}, fields=selected)


@router.patch("/{id}", response_model=ProjectGroupOut, dependencies=[Depends(require_user)])
async def update_one_by_identity(
    service: ProjectGroupServiceDep,
    id: str,
    update: ProjectGroupPatch,
):
    """Partially update the project group identified by its ``_id``."""
    return await service.update_one({"id": id}, update=update)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_user)])
async def delete_one_by_identity(
    service: ProjectGroupServiceDep,
    id: str,
):
    """Delete the project group identified by its ``_id``. Restricted to its owner or an admin."""
    await service.delete_one({"id": id})
    return Response(status_code=status.HTTP_204_NO_CONTENT)
