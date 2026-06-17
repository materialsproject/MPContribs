from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from fastapi_filter import FilterDepends

from mpcontribs_api.dependencies import S3Dep
from mpcontribs_api.domains._shared.bulk import BulkWriteSummary
from mpcontribs_api.domains._shared.models import ComponentDeleteResponse
from mpcontribs_api.domains._shared.types import (
    DownloadFormat,
    FieldSelector,
    ShortMimeFormat,
    download_filename,
)
from mpcontribs_api.domains.tables.dependencies import TableDep, TableServiceDep
from mpcontribs_api.domains.tables.models import Table, TableFilter, TableIn, TableOut, TablePatch
from mpcontribs_api.pagination import CursorParams, Page

router = APIRouter()


@router.get("", response_model=Page[TableOut])
async def get_tables(
    repo: TableDep,
    pagination: Annotated[CursorParams, Depends()],
    filter: TableFilter = FilterDepends(TableFilter),
    fields: FieldSelector = TableOut.default_fields(),
):
    selected = TableOut.parse_fields(fields)
    return await repo.get_tables(filter=filter, fields=selected, pagination=pagination)


@router.get("/{pk}", response_model=TableOut)
async def get_table(
    repo: TableDep,
    pk: str,
    fields: FieldSelector = TableOut.default_fields(),
):
    selected = TableOut.parse_fields(fields)
    return await repo.get_table_by_id(id=pk, fields=selected)


@router.get("/download/{short_mime}")
async def download_table(
    repo: TableDep,
    s3: S3Dep,
    format: DownloadFormat,
    short_mime: ShortMimeFormat = ShortMimeFormat.GZ,
    ignore_cache: bool = False,
    filter: TableFilter = FilterDepends(TableFilter),
    fields: FieldSelector = TableOut.default_fields(),
) -> StreamingResponse:
    selected = TableOut.parse_fields(fields)
    body = await repo.download_tables(
        format=format,
        short_mime=short_mime,
        ignore_cache=ignore_cache,
        filter=filter,
        fields=selected,
        s3=s3,
        bucket_name="tables",
        key_name="",  # TODO: Temp
    )
    filename = download_filename("tables", format, short_mime)
    return StreamingResponse(
        body,
        media_type="application/gzip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("", response_model=BulkWriteSummary[Table])
async def insert_tables(
    repo: TableDep,
    tables: list[TableIn],
):
    return await repo.insert_tables(tables=tables)


@router.delete("", response_model=ComponentDeleteResponse)
async def delete_tables(service: TableServiceDep, filter: TableFilter = FilterDepends(TableFilter)):
    return await service.delete(filter=filter)


@router.delete("/{id}", response_model=ComponentDeleteResponse)
async def delete_table_by_id(service: TableServiceDep, id: str):
    return await service.delete_by_id(id=id)


@router.patch("/{id}")
async def patch_table_by_id(
    repo: TableDep,
    id: str,
    update: TablePatch,
):
    return await repo.patch_table_by_id(id=id, update=update)
