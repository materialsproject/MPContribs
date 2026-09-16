from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from fastapi_filter import FilterDepends

from mpcontribs_api.dependencies import S3Dep, require_user, require_writer
from mpcontribs_api.domains._shared.bulk import BulkWriteSummary
from mpcontribs_api.domains._shared.models import ComponentDeleteResponse, ComponentIdentity
from mpcontribs_api.domains._shared.types import (
    DownloadFormat,
    FieldSelector,
    ShortMimeFormat,
    download_filename,
)
from mpcontribs_api.domains.tables.dependencies import TableServiceDep
from mpcontribs_api.domains.tables.models import Table, TableFilter, TableIn, TableOut, TablePatch
from mpcontribs_api.pagination import CursorParams, Page

router = APIRouter()


@router.get("", response_model=None)
async def read_many(
    service: TableServiceDep,
    pagination: Annotated[CursorParams, Depends()],
    filter: TableFilter = FilterDepends(TableFilter),
    fields: FieldSelector = None,
) -> Page[TableOut]:
    selected = TableOut.parse_fields(fields)
    return await service.read_many(filter=filter, fields=selected, pagination=pagination)


@router.get("/item", response_model=None)
async def read_one_by_identity(
    service: TableServiceDep,
    identity: Annotated[ComponentIdentity, Depends()],
    fields: FieldSelector = None,
) -> TableOut:
    """Return a single table addressed by its content ``md5`` (its natural key)."""
    selected = TableOut.parse_fields(fields)
    return await service.read_one(identifiers=identity.as_dict(), fields=selected)


@router.delete("/item", response_model=ComponentDeleteResponse, dependencies=[Depends(require_user)])
async def delete_one_by_identity(
    service: TableServiceDep, identity: Annotated[ComponentIdentity, Depends()]
) -> ComponentDeleteResponse:
    """Delete a single table addressed by its content ``md5`` (its natural key)."""
    return await service.delete_one(identifiers=identity.as_dict())


@router.patch("/item", response_model=TableOut, dependencies=[Depends(require_user)])
async def update_one_by_identity(
    service: TableServiceDep,
    identity: Annotated[ComponentIdentity, Depends()],
    update: TablePatch,
) -> Table:
    """Patch a single table addressed by its content ``md5`` (its natural key)."""
    return await service.update_one(identifiers=identity.as_dict(), update=update)


@router.get("/{id}", response_model=None)
async def read_one(
    service: TableServiceDep,
    id: str,
    fields: FieldSelector = None,
) -> TableOut:
    """Return a single table addressed by its ``_id``."""
    selected = TableOut.parse_fields(fields)
    return await service.read_one(identifiers={"id": id}, fields=selected)


@router.get("/download/{short_mime}")
async def download_table(
    service: TableServiceDep,
    s3: S3Dep,
    format: DownloadFormat,
    short_mime: ShortMimeFormat = ShortMimeFormat.GZ,
    ignore_cache: bool = False,
    filter: TableFilter = FilterDepends(TableFilter),
    fields: FieldSelector = None,
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


@router.post("", response_model=BulkWriteSummary[TableOut], dependencies=[Depends(require_writer)])
async def insert_many(
    service: TableServiceDep,
    tables: list[TableIn],
) -> BulkWriteSummary[Table]:  # succeeded items rendered as TableOut via response_model
    return await service.insert_many(components=tables)


@router.delete("", response_model=ComponentDeleteResponse, dependencies=[Depends(require_user)])
async def delete_many(
    service: TableServiceDep, filter: TableFilter = FilterDepends(TableFilter)
) -> ComponentDeleteResponse:
    return await service.delete_many(filter=filter)


@router.delete("/{id}", response_model=ComponentDeleteResponse, dependencies=[Depends(require_user)])
async def delete_one(service: TableServiceDep, id: str) -> ComponentDeleteResponse:
    """Delete a single table addressed by its ``_id``"""
    return await service.delete_one(identifiers={"id": id})


@router.patch("/{id}", response_model=TableOut, dependencies=[Depends(require_user)])
async def update_one(
    service: TableServiceDep,
    id: str,
    update: TablePatch,
) -> Table:
    """Patch a single table addressed by its ``_id``."""
    return await service.update_one(identifiers={"id": id}, update=update)
