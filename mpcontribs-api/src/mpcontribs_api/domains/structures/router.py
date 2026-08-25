from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from fastapi_filter import FilterDepends

from mpcontribs_api.dependencies import S3Dep, require_user, require_writer
from mpcontribs_api.domains._shared.bulk import BulkWriteSummary
from mpcontribs_api.domains._shared.models import ComponentDeleteResponse
from mpcontribs_api.domains._shared.types import (
    DownloadFormat,
    FieldSelector,
    ShortMimeFormat,
    download_filename,
)
from mpcontribs_api.domains.structures.dependencies import StructureServiceDep
from mpcontribs_api.domains.structures.models import StructureFilter, StructureIn, StructureOut, StructurePatch
from mpcontribs_api.pagination import CursorParams

router = APIRouter()


@router.get("")
async def read_many(
    service: StructureServiceDep,
    pagination: Annotated[CursorParams, Depends()],
    filter: StructureFilter = FilterDepends(StructureFilter),
    fields: FieldSelector = None,
):
    selected = StructureOut.parse_fields(fields)
    return await service.read_many(filter=filter, fields=selected, pagination=pagination)


@router.get("/{id}")
async def read_one(
    service: StructureServiceDep,
    id: str,
    fields: FieldSelector = None,
):
    """Return a single structure addressed by its ``_id`` or its content ``md5``."""
    selected = StructureOut.parse_fields(fields)
    return await service.read_one(identifiers={"id": id}, fields=selected)


@router.get("/download/{short_mime}")
async def download_structure(
    service: StructureServiceDep,
    format: DownloadFormat,
    s3: S3Dep,
    short_mime: ShortMimeFormat = ShortMimeFormat.GZ,
    ignore_cache: bool = False,
    filter: StructureFilter = FilterDepends(StructureFilter),
    fields: FieldSelector = None,
) -> StreamingResponse:
    selected = StructureOut.parse_fields(fields)
    body = await service.download(
        format=format,
        short_mime=short_mime,
        ignore_cache=ignore_cache,
        filter=filter,
        fields=selected,
        s3=s3,
    )
    filename = download_filename("structures", format, short_mime)
    return StreamingResponse(
        body,
        media_type="application/gzip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("", response_model=BulkWriteSummary[StructureOut], dependencies=[Depends(require_writer)])
async def insert_many(
    service: StructureServiceDep,
    structures: list[StructureIn],
):
    return await service.insert_many(components=structures)


@router.delete("", response_model=ComponentDeleteResponse, dependencies=[Depends(require_user)])
async def delete_many(service: StructureServiceDep, filter: StructureFilter = FilterDepends(StructureFilter)):
    return await service.delete_many(filter=filter)


@router.delete("/{id}", response_model=ComponentDeleteResponse, dependencies=[Depends(require_user)])
async def delete_one(service: StructureServiceDep, id: str):
    """Delete a single structure addressed by its ``_id`` or its content ``md5``."""
    return await service.delete_one(identifiers={"id": id})


@router.patch("/{id}", dependencies=[Depends(require_user)])
async def update_one(
    service: StructureServiceDep,
    id: str,
    update: StructurePatch,
):
    """Patch a single structure addressed by its ``_id`` or its content ``md5``."""
    return await service.update_one(identifiers={"id": id}, update=update)
