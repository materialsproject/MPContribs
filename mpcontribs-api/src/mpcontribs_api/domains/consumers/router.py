from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from fastapi_filter import FilterDepends

from mpcontribs_api.dependencies import require_admin
from mpcontribs_api.domains._shared.types import FieldSelector
from mpcontribs_api.domains.consumers.dependencies import ConsumerServiceDep
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
async def read_many(
    service: ConsumerServiceDep,
    pagination: Annotated[CursorParams, Depends()],
    filter: ConsumerFilter = FilterDepends(ConsumerFilter),
    fields: FieldSelector = None,
):
    """List consumer overrides (admin only)."""
    selected = ConsumerOut.parse_fields(fields)
    return await service.read_many(filter=filter, pagination=pagination, fields=selected)


@router.get("/item")
async def read_one_by_identity(
    consumer_id: str,
    service: ConsumerServiceDep,
    fields: FieldSelector = None,
):
    """Get a single consumer override by its natural key, Kong's ``consumer_id`` (admin only)."""
    selected = ConsumerOut.parse_fields(fields)
    return await service.read_one({"consumer_id": consumer_id}, fields=selected)


@router.patch("/item", response_model=ConsumerOut)
async def update_one_by_identity(
    service: ConsumerServiceDep,
    consumer_id: str,
    update: ConsumerPatch,
):
    """Partially update a consumer override by its ``consumer_id`` natural key (admin only)."""
    return await service.update_one({"consumer_id": consumer_id}, update)


@router.delete("/item", status_code=status.HTTP_204_NO_CONTENT)
async def delete_one_by_identity(
    service: ConsumerServiceDep,
    consumer_id: str,
):
    """Delete a consumer override by its ``consumer_id`` natural key (admin only)."""
    await service.delete_one({"consumer_id": consumer_id})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{id}")
async def read_one(
    id: str,
    service: ConsumerServiceDep,
    fields: FieldSelector = None,
):
    """Get a single consumer override by document id (admin only)."""
    selected = ConsumerOut.parse_fields(fields)
    return await service.read_one({"id": id}, fields=selected)


@router.post("", response_model=ConsumerOut, status_code=status.HTTP_201_CREATED)
async def insert_one(
    service: ConsumerServiceDep,
    consumer: ConsumerIn,
):
    """Create a new consumer override, rejecting a duplicate ``consumer_id`` with 409 (admin only)."""
    return await service.insert_one(consumer)


@router.patch("/{id}", response_model=ConsumerOut)
async def update_one(
    service: ConsumerServiceDep,
    id: str,
    update: ConsumerPatch,
):
    """Partially update a consumer override by document id (admin only)."""
    return await service.update_one({"id": id}, update)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_one(
    service: ConsumerServiceDep,
    id: str,
):
    """Delete a consumer override by document id (admin only)."""
    await service.delete_one({"id": id})
    return Response(status_code=status.HTTP_204_NO_CONTENT)
