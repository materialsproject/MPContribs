from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from fastapi_filter import FilterDepends

from mpcontribs_api.dependencies import require_user
from mpcontribs_api.domains._shared.types import FieldSelector
from mpcontribs_api.domains.initiatives.dependencies import InitiativeServiceDep
from mpcontribs_api.domains.initiatives.models import (
    InitiativeFilter,
    InitiativeIn,
    InitiativeOut,
    InitiativePatch,
)
from mpcontribs_api.pagination import CursorParams

router = APIRouter()


@router.get("")
async def get_many(
    service: InitiativeServiceDep,
    pagination: Annotated[CursorParams, Depends()],
    filter: InitiativeFilter = FilterDepends(InitiativeFilter),
    fields: FieldSelector = None,
):
    """Return paginated initiatives matching a filter, scoped to the caller."""
    selected = InitiativeOut.parse_fields(fields)
    return await service.get_many(pagination=pagination, filter=filter, fields=selected)


@router.get("/{slug}")
async def get_one(
    service: InitiativeServiceDep,
    slug: str,
    fields: FieldSelector = None,
):
    """Return the single initiative identified by ``slug``, scoped to the caller."""
    selected = InitiativeOut.parse_fields(fields)
    return await service.get_one({"slug": slug}, fields=selected)


@router.post(
    "", response_model=InitiativeOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_user)]
)
async def insert_one(
    service: InitiativeServiceDep,
    initiative: InitiativeIn,
):
    """Create a new initiative owned by the caller.

    Starts unapproved and private. Rejected with 409 if the caller already owns the maximum number
    of unapproved initiatives, or if the slug is already taken.
    """
    return await service.insert_one(data=initiative)


@router.patch("/{slug}", response_model=InitiativeOut, dependencies=[Depends(require_user)])
async def patch_one(
    service: InitiativeServiceDep,
    slug: str,
    update: InitiativePatch,
):
    """Partially update the initiative identified by ``slug``.

    Requires manage rights (owner/collaborator/admin). ``is_approved`` is admin-only, and an
    initiative cannot be made public until it is approved.
    """
    return await service.patch_one({"slug": slug}, update=update)


@router.delete("/{slug}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_user)])
async def delete_one(
    service: InitiativeServiceDep,
    slug: str,
):
    """Delete the initiative identified by ``slug``. Restricted to its owner or an admin."""
    await service.delete_one({"slug": slug})
    return Response(status_code=status.HTTP_204_NO_CONTENT)
