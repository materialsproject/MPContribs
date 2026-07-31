from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from fastapi_filter import FilterDepends

from mpcontribs_api.dependencies import require_admin
from mpcontribs_api.domains._shared.types import FieldSelector
from mpcontribs_api.domains.consumers.dependencies import ConsumerDep
from mpcontribs_api.domains.consumers.models import (
    ConsumerFilter,
    ConsumerIn,
    ConsumerOut,
    ConsumerPatch,
)
from mpcontribs_api.pagination import CursorParams

# Admin-only override management. Every route depends on ``require_admin``; the router as a whole is
# mounted with ``include_in_schema=False`` (see api/v1/router.py) so it is hidden from the OpenAPI
# spec while remaining reachable by callers that know the path.
router = APIRouter(dependencies=[Depends(require_admin)])


@router.get("")
async def get_consumers(
    repo: ConsumerDep,
    pagination: Annotated[CursorParams, Depends()],
    filter: ConsumerFilter = FilterDepends(ConsumerFilter),
    fields: FieldSelector = ConsumerOut.default_fields(),
):
    """List consumer overrides (admin only)."""
    selected = ConsumerOut.parse_fields(fields)
    return await repo.get_consumers(filter=filter, pagination=pagination, fields=selected)


@router.get("/{id}")
async def get_consumer_by_id(
    id: str,
    repo: ConsumerDep,
    fields: FieldSelector = ConsumerOut.default_fields(),
):
    """Get a single consumer override by document id (admin only)."""
    selected = ConsumerOut.parse_fields(fields)
    return await repo.get_consumer_by_id(id=id, fields=selected)


@router.post("", response_model=ConsumerOut, status_code=status.HTTP_201_CREATED)
async def create_consumer(
    repo: ConsumerDep,
    consumer: ConsumerIn,
):
    """Create a new consumer override, rejecting a duplicate ``consumer_id`` with 409 (admin only)."""
    return await repo.insert_consumer(consumer)


@router.patch("/{id}", response_model=ConsumerOut)
async def patch_consumer_by_id(
    repo: ConsumerDep,
    id: str,
    update: ConsumerPatch,
):
    """Partially update a consumer override by document id (admin only)."""
    return await repo.patch_consumer_by_id(id=id, update=update)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_consumer_by_id(
    repo: ConsumerDep,
    id: str,
):
    """Delete a consumer override by document id (admin only)."""
    await repo.delete_consumer_by_id(id=id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
