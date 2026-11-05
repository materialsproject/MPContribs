from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from fastapi_filter import FilterDepends

from mpcontribs_api.dependencies import S3Dep
from mpcontribs_api.domains._shared.types import FieldSelector
from mpcontribs_api.domains.components.models import ComponentIdentity
from mpcontribs_api.domains.structures.dependencies import StructureServiceDep
from mpcontribs_api.domains.structures.models import StructureFilter, StructureOut
from mpcontribs_api.pagination import CursorParams, Page

# Structures are immutable, worker-written S3 objects: these endpoints are read-only. Creation,
# replacement, and deletion all flow through the /uploads endpoints.
router = APIRouter()


@router.get("", response_model_exclude_unset=True)
async def read_many(
    service: StructureServiceDep,
    pagination: Annotated[CursorParams, Depends()],
    filter: StructureFilter = FilterDepends(StructureFilter),
    fields: FieldSelector = None,
) -> Page[StructureOut]:
    selected = StructureOut.parse_fields(fields)
    return await service.read_many(filter=filter, fields=selected, pagination=pagination)


@router.get("/item", response_model_exclude_unset=True)
async def read_one_by_identity(
    service: StructureServiceDep,
    identity: Annotated[ComponentIdentity, Depends()],
    fields: FieldSelector = None,
) -> StructureOut | None:
    """Return the structure addressed by its content-addressed location (``project``, ``hash``), or None."""
    selected = StructureOut.parse_fields(fields)
    return await service.read_one(identifiers=identity.as_dict(), fields=selected)


@router.get("/{id}", response_model_exclude_unset=True)
async def read_one(
    service: StructureServiceDep,
    id: str,
    fields: FieldSelector = None,
) -> StructureOut | None:
    """Return the structure addressed by its ``_id``, or None when none matches."""
    selected = StructureOut.parse_fields(fields)
    return await service.read_one(identifiers={"id": id}, fields=selected)


@router.get("/{id}/content")
async def read_structure_content(
    service: StructureServiceDep,
    id: str,
    s3: S3Dep,
) -> RedirectResponse:
    """Redirect (307) to a short-lived presigned GET URL for the structure object in S3."""
    url = await service.read_content(identifiers={"id": id}, s3=s3)
    return RedirectResponse(url, status_code=307)
