from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from fastapi_filter import FilterDepends
from starlette.status import HTTP_204_NO_CONTENT

from mpcontribs_api.dependencies import require_user
from mpcontribs_api.domains._shared.types import FieldSelector
from mpcontribs_api.domains.projects.dependencies import ProjectServiceDep
from mpcontribs_api.domains.projects.models import (
    ProjectFilter,
    ProjectIn,
    ProjectOut,
    ProjectPatch,
)
from mpcontribs_api.pagination import CursorParams

router = APIRouter()


@router.get("")
async def get_projects(
    service: ProjectServiceDep,
    pagination: Annotated[CursorParams, Depends()],
    filter: ProjectFilter = FilterDepends(ProjectFilter),
    fields: FieldSelector = None,
):
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
    return await service.get_many(filter=filter, pagination=pagination, fields=selected)


@router.get("/{id}")
async def get_one(
    id: str,
    service: ProjectServiceDep,
    fields: FieldSelector = None,
):
    """Gets a single project by its ID.

    Args:
        id (str): the id of the project to retrieve
        service (ProjectServiceDep): the project service we depend on
        fields (list[str] | None): optional ``_fields`` selection. Omitted -> server defaults;
            empty (``?_fields=``) -> identity fields only; ``_all`` -> the full document

    Returns:
        ProjectOut: the requested project, actual data returned is determined by the view the user requested
    """
    selected = ProjectOut.parse_fields(fields)
    return await service.get_one({"id": id}, fields=selected)


@router.put("/{id}", response_model=ProjectOut, dependencies=[Depends(require_user)])
async def upsert_one(
    service: ProjectServiceDep,
    id: str,
    project: ProjectIn,
):
    """Upsert a project by provided id.

    Upsert: Update document if id is found, otherwise insert new document using id.
    Note: Relies on the path param 'id' for finding, rather than the body's id.

    Args:
        service (ProjectServiceDep): the project service we depend on
        id (str): the id of the project to retrieve
        project (ProjectIn): the data of the project to upsert

    Returns:
        ProjectOut: the full document that either replaced an old one or was inserted
    """
    return await service.upsert_one({"id": id}, data=project)


@router.patch("/{id}", response_model=ProjectOut, dependencies=[Depends(require_user)])
async def patch_one(
    service: ProjectServiceDep,
    id: str,
    update: ProjectPatch,
):
    """Partial update to project identified with 'id'.

    Note: overwrites fields with given values - arrays are not appended to.

    The ``initiative`` field carries an initiative ``slug`` (or ``null`` to unassign). Setting it
    is gated by the assignment service: the caller must be able to manage the target initiative
    (owner/collaborator/admin) and an unapproved initiative may not exceed its member cap. Plain
    field patches take the fast path straight to the repository.

    Args:
        service (ProjectServiceDep): the project assignment service we depend on
        id (str): the id of the project to update
        update (ProjectPatch): the partial update to apply - unset fields are dropped
            - Note: If fields are intentionally set to None, None is applied to the field.

    Returns:
        ProjectOut: the full Project with updates applied
    """
    return await service.patch_one({"id": id}, update=update)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_user)])
async def delete_one(
    service: ProjectServiceDep,
    id: str,
):
    """Deletes a project matching id.

    Args:
        service (ProjectServiceDep): the project service we depend on
        id (str): the id of the project to be deleted
    Returns:
        Response: a response with the 204 response code (rather than FastAPIs default 200)
    """
    await service.delete_one({"id": id})
    return Response(status_code=HTTP_204_NO_CONTENT)
