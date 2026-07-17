from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from fastapi_filter import FilterDepends

from mpcontribs_api.dependencies import require_user
from mpcontribs_api.domains._shared.types import FieldSelector
from mpcontribs_api.domains.initiatives.dependencies import InitiativeDep
from mpcontribs_api.domains.initiatives.models import (
    InitiativeFilter,
    InitiativeIn,
    InitiativeOut,
    InitiativePatch,
)
from mpcontribs_api.pagination import CursorParams

router = APIRouter()


@router.get("")
async def get_initiatives(
    repo: InitiativeDep,
    pagination: Annotated[CursorParams, Depends()],
    filter: InitiativeFilter = FilterDepends(InitiativeFilter),
    fields: FieldSelector = InitiativeOut.default_fields(),
):
    """Return paginated initiatives matching a filter, scoped to the caller."""
    selected = InitiativeOut.parse_fields(fields)
    return await repo.get_initiatives(pagination=pagination, filter=filter, fields=selected)


@router.get("/{slug}")
async def get_initiative(
    repo: InitiativeDep,
    slug: str,
    fields: FieldSelector = InitiativeOut.default_fields(),
):
    """Return the single initiative identified by ``slug``, scoped to the caller."""
    selected = InitiativeOut.parse_fields(fields)
    return await repo.get_initiative(slug=slug, fields=selected)


@router.post(
    "", response_model=InitiativeOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_user)]
)
async def insert_initiative(
    repo: InitiativeDep,
    initiative: InitiativeIn,
):
    """Create a new initiative owned by the caller.

    Starts unapproved and private. Rejected with 409 if the caller already owns the maximum number
    of unapproved initiatives, or if the slug is already taken.
    """
    return await repo.insert_initiative(data=initiative)


@router.patch("/{slug}", response_model=InitiativeOut, dependencies=[Depends(require_user)])
async def patch_initiative(
    repo: InitiativeDep,
    slug: str,
    update: InitiativePatch,
):
    """Partially update the initiative identified by ``slug``.

    Requires manage rights (owner/collaborator/admin). ``is_approved`` is admin-only, and an
    initiative cannot be made public until it is approved.
    """
    return await repo.patch_initiative(slug=slug, update=update)


@router.delete("/{slug}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_user)])
async def delete_initiative(
    repo: InitiativeDep,
    slug: str,
):
    """Delete the initiative identified by ``slug``. Restricted to its owner or an admin."""
    await repo.delete_initiative(slug=slug)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
