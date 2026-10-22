from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from fastapi_filter import FilterDepends

from mpcontribs_api.dependencies import S3Dep, require_user
from mpcontribs_api.domains._shared.models import DeleteResult
from mpcontribs_api.domains._shared.types import (
    FieldSelector,
)
from mpcontribs_api.domains.structures.dependencies import StructureServiceDep
from mpcontribs_api.domains.structures.models import StructureFilter, StructureOut, StructureVersionIdentity
from mpcontribs_api.pagination import CursorParams, Page

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
    identity: Annotated[StructureVersionIdentity, Depends()],
    fields: FieldSelector = None,
) -> StructureOut | None:
    """Return the structure version addressed by its S3 ``s3_version_id`` (its natural key), or None."""
    selected = StructureOut.parse_fields(fields)
    return await service.read_one(identifiers=identity.as_dict(), fields=selected)


@router.delete("/item", dependencies=[Depends(require_user)])
async def delete_one_by_identity(
    service: StructureServiceDep, identity: Annotated[StructureVersionIdentity, Depends()]
) -> DeleteResult:
    """Delete a single structure version addressed by its ``s3_version_id`` (its natural key)."""
    return await service.delete_one(identifiers=identity.as_dict())


@router.get("/{id}", response_model_exclude_unset=True)
async def read_one(
    service: StructureServiceDep,
    id: str,
    fields: FieldSelector = None,
) -> StructureOut | None:
    """Return the structure version addressed by its ``_id``, or None when none matches."""
    selected = StructureOut.parse_fields(fields)
    return await service.read_one(identifiers={"id": id}, fields=selected)


@router.get("/{id}/content")
async def read_structure_content(
    service: StructureServiceDep,
    id: str,
    s3: S3Dep,
) -> RedirectResponse:
    """Redirect (307) to a short-lived presigned GET URL for the version-pinned structure object."""
    url = await service.read_content(identifiers={"id": id}, s3=s3)
    return RedirectResponse(url, status_code=307)


@router.delete("", dependencies=[Depends(require_user)])
async def delete_many(
    service: StructureServiceDep, filter: StructureFilter = FilterDepends(StructureFilter)
) -> DeleteResult:
    return await service.delete_many(filter=filter)


@router.delete("/{id}", dependencies=[Depends(require_user)])
async def delete_one(service: StructureServiceDep, id: str) -> DeleteResult:
    """Delete a single structure version addressed by its ``_id``."""
    return await service.delete_one(identifiers={"id": id})
