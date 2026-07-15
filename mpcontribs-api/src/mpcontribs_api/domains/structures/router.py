from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from fastapi_filter import FilterDepends

from mpcontribs_api.dependencies import S3Dep, require_user
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
async def get_structures(
    service: StructureServiceDep,
    pagination: Annotated[CursorParams, Depends()],
    filter: StructureFilter = FilterDepends(StructureFilter),
    fields: FieldSelector = StructureOut.default_fields(),
):
    selected = StructureOut.parse_fields(fields)
    return await service.get_many(filter=filter, fields=selected, pagination=pagination)


@router.get("/{pk}")
async def get_structure(
    service: StructureServiceDep,
    pk: str,
    fields: FieldSelector = StructureOut.default_fields(),
):
    selected = StructureOut.parse_fields(fields)
    return await service.get_by_id(id=pk, fields=selected)


@router.get("/download/{short_mime}")
async def download_structure(
    service: StructureServiceDep,
    format: DownloadFormat,
    s3: S3Dep,
    short_mime: ShortMimeFormat = ShortMimeFormat.GZ,
    ignore_cache: bool = False,
    filter: StructureFilter = FilterDepends(StructureFilter),
    fields: FieldSelector = StructureOut.default_fields(),
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


@router.post("", response_model=BulkWriteSummary[StructureOut], dependencies=[Depends(require_user)])
async def insert_structures(
    service: StructureServiceDep,
    structures: list[StructureIn],
):
    return await service.insert(components=structures)


@router.delete("", response_model=ComponentDeleteResponse, dependencies=[Depends(require_user)])
async def delete_structures(service: StructureServiceDep, filter: StructureFilter = FilterDepends(StructureFilter)):
    return await service.delete(filter=filter)


@router.delete("/{id}", response_model=ComponentDeleteResponse, dependencies=[Depends(require_user)])
async def delete_structure_by_id(service: StructureServiceDep, id: str):
    return await service.delete_by_id(id=id)


@router.patch("/{id}", dependencies=[Depends(require_user)])
async def patch_structure_by_id(
    service: StructureServiceDep,
    id: str,
    update: StructurePatch,
):
    return await service.patch_by_id(id=id, update=update)
