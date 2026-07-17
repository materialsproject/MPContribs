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
from mpcontribs_api.domains.tables.dependencies import TableServiceDep
from mpcontribs_api.domains.tables.models import Table, TableFilter, TableIn, TableOut, TablePatch
from mpcontribs_api.pagination import CursorParams

router = APIRouter()


@router.get("")
async def get_tables(
    service: TableServiceDep,
    pagination: Annotated[CursorParams, Depends()],
    filter: TableFilter = FilterDepends(TableFilter),
    fields: FieldSelector = TableOut.default_fields(),
):
    selected = TableOut.parse_fields(fields)
    return await service.get_many(filter=filter, fields=selected, pagination=pagination)


@router.get("/{pk}")
async def get_table(
    service: TableServiceDep,
    pk: str,
    fields: FieldSelector = TableOut.default_fields(),
):
    selected = TableOut.parse_fields(fields)
    return await service.get_by_id(id=pk, fields=selected)


@router.get("/download/{short_mime}")
async def download_table(
    service: TableServiceDep,
    s3: S3Dep,
    format: DownloadFormat,
    short_mime: ShortMimeFormat = ShortMimeFormat.GZ,
    ignore_cache: bool = False,
    filter: TableFilter = FilterDepends(TableFilter),
    fields: FieldSelector = TableOut.default_fields(),
) -> StreamingResponse:
    selected = TableOut.parse_fields(fields)
    body = await service.download(
        format=format,
        short_mime=short_mime,
        ignore_cache=ignore_cache,
        filter=filter,
        fields=selected,
        s3=s3,
    )
    filename = download_filename("tables", format, short_mime)
    return StreamingResponse(
        body,
        media_type="application/gzip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("", response_model=BulkWriteSummary[Table], dependencies=[Depends(require_writer)])
async def insert_tables(
    service: TableServiceDep,
    tables: list[TableIn],
):
    return await service.insert(components=tables)


@router.delete("", response_model=ComponentDeleteResponse, dependencies=[Depends(require_user)])
async def delete_tables(service: TableServiceDep, filter: TableFilter = FilterDepends(TableFilter)):
    return await service.delete(filter=filter)


@router.delete("/{id}", response_model=ComponentDeleteResponse, dependencies=[Depends(require_user)])
async def delete_table_by_id(service: TableServiceDep, id: str):
    return await service.delete_by_id(id=id)


@router.patch("/{id}", dependencies=[Depends(require_user)])
async def patch_table_by_id(
    service: TableServiceDep,
    id: str,
    update: TablePatch,
):
    return await service.patch_by_id(id=id, update=update)
