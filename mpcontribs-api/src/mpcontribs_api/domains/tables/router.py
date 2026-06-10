from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response
from fastapi.responses import StreamingResponse
from fastapi_filter import FilterDepends

from mpcontribs_api.domains._shared.bulk import BulkWriteSummary
from mpcontribs_api.domains._shared.models import DeleteResponse
from mpcontribs_api.domains._shared.types import DownloadFormat, FieldSelector
from mpcontribs_api.domains.tables.dependencies import TableDep
from mpcontribs_api.domains.tables.models import Table, TableFilter, TableIn, TableOut, TablePatch
from mpcontribs_api.pagination import CursorParams, Page

router = APIRouter(tags=["components", "tables"])


@router.get("", response_model=Page[TableOut])
async def get_tables(
    repo: TableDep,
    pagination: Annotated[CursorParams, Depends()],
    filter: TableFilter = FilterDepends(TableFilter),
    fields: FieldSelector = TableOut.default_fields(),
):
    selected = TableOut.parse_fields(fields)
    return await repo.get_tables(filter=filter, fields=selected, pagination=pagination)


@router.get("{pk}", response_model=TableOut)
async def get_table(
    repo: TableDep,
    pk: str,
    fields: FieldSelector = TableOut.default_fields(),
):
    selected = TableOut.parse_fields(fields)
    return await repo.get_table_by_id(id=pk, fields=selected)


@router.get("download/{short_mime}")
async def download_table(
    repo: TableDep,
    response: Response,
    format: DownloadFormat,
    short_mime: Literal["gz", None] = "gz",
    ignore_cache: bool = False,
    filter: TableFilter = FilterDepends(TableFilter),
    fields: FieldSelector = TableOut.default_fields(),
) -> StreamingResponse:
    selected = TableOut.parse_fields(fields)
    body = repo.download_tables(
        format=format,
        short_mime=short_mime,
        ignore_cache=ignore_cache,
        filter=filter,
        fields=selected,
    )
    return StreamingResponse(
        body,
        media_type="application/gzip",
        headers={"Content-Disposition": 'attachment; filename="tables.jsonl.gz"'},
    )


@router.post("", response_model=BulkWriteSummary[Table])
async def insert_tables(
    repo: TableDep,
    tables: list[TableIn],
):
    return await repo.insert_tables(tables=tables)


@router.delete("", response_model=DeleteResponse)
async def delete_tables(repo: TableDep, filter: TableFilter = FilterDepends(TableFilter)):
    return await repo.delete_tables(filter=filter)


@router.delete("{id}", response_model=DeleteResponse)
async def delete_table_by_id(repo: TableDep, id: str):
    return await repo.delete_table_by_id(id=id)


@router.patch("{id}")
async def patch_table_by_id(
    repo: TableDep,
    id: str,
    update: TablePatch,
):
    return await repo.patch_table_by_id(id=id, update=update)
