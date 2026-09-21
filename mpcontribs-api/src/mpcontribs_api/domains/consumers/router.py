from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from fastapi_filter import FilterDepends

from mpcontribs_api.dependencies import require_admin
from mpcontribs_api.domains._shared.types import FieldSelector
from mpcontribs_api.domains.consumers.dependencies import ConsumerServiceDep
from mpcontribs_api.domains.consumers.models import (
    ConsumerFilter,
    ConsumerIdentity,
    ConsumerIn,
    ConsumerOut,
    ConsumerPatch,
)
from mpcontribs_api.pagination import CursorParams, Page

# Admin-only override management. Every route depends on ``require_admin``; the router as a whole is
# mounted with ``include_in_schema=False`` (see api/v1/router.py) so it is hidden from the OpenAPI
# spec while remaining reachable by callers that know the path.
router = APIRouter(dependencies=[Depends(require_admin)])


@router.get("", response_model_exclude_unset=True)
async def read_many(
    service: ConsumerServiceDep,
    pagination: Annotated[CursorParams, Depends()],
    filter: ConsumerFilter = FilterDepends(ConsumerFilter),
    fields: FieldSelector = None,
) -> Page[ConsumerOut]:
    """List consumer overrides (admin only)."""
    selected = ConsumerOut.parse_fields(fields)
    return await service.read_many(filter=filter, pagination=pagination, fields=selected)


@router.get("/item", response_model_exclude_unset=True)
async def read_one_by_identity(
    identity: Annotated[ConsumerIdentity, Depends()],
    service: ConsumerServiceDep,
    fields: FieldSelector = None,
) -> ConsumerOut | None:
    """Get a consumer override by its natural key, Kong's ``consumer_id``, or None when none matches (admin only)."""
    selected = ConsumerOut.parse_fields(fields)
    return await service.read_one(identity.as_dict(), fields=selected)


@router.patch("/item")
async def update_one_by_identity(
    service: ConsumerServiceDep,
    identity: Annotated[ConsumerIdentity, Depends()],
    update: ConsumerPatch,
) -> ConsumerOut:
    """Partially update a consumer override by its ``consumer_id`` natural key (admin only)."""
    return await service.update_one(identity.as_dict(), update)


@router.delete("/item", status_code=status.HTTP_204_NO_CONTENT)
async def delete_one_by_identity(
    service: ConsumerServiceDep,
    identity: Annotated[ConsumerIdentity, Depends()],
) -> Response:
    """Delete a consumer override by its ``consumer_id`` natural key (admin only)."""
    await service.delete_one(identity.as_dict())
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{id}", response_model_exclude_unset=True)
async def read_one(
    id: str,
    service: ConsumerServiceDep,
    fields: FieldSelector = None,
) -> ConsumerOut | None:
    """Get a single consumer override by document id, or None when none matches (admin only)."""
    selected = ConsumerOut.parse_fields(fields)
    return await service.read_one({"id": id}, fields=selected)


@router.post("", status_code=status.HTTP_201_CREATED)
async def insert_one(
    service: ConsumerServiceDep,
    consumer: ConsumerIn,
) -> ConsumerOut:
    """Create a new consumer override, rejecting a duplicate ``consumer_id`` with 409 (admin only)."""
    return await service.insert_one(consumer)


@router.patch("/{id}")
async def update_one(
    service: ConsumerServiceDep,
    id: str,
    update: ConsumerPatch,
) -> ConsumerOut:
    """Partially update a consumer override by document id (admin only)."""
    return await service.update_one({"id": id}, update)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_one(
    service: ConsumerServiceDep,
    id: str,
) -> Response:
    """Delete a consumer override by document id (admin only)."""
    await service.delete_one({"id": id})
    return Response(status_code=status.HTTP_204_NO_CONTENT)
