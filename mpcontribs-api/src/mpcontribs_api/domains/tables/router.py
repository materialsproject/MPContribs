from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi_filter import FilterDepends

from mpcontribs_api.dependencies import require_user, require_writer
from mpcontribs_api.domains._shared.bulk import BulkWriteSummary
from mpcontribs_api.domains._shared.models import ComponentDeleteResponse, ComponentIdentity
from mpcontribs_api.domains._shared.types import DownloadFormat, FieldSelector
from mpcontribs_api.domains.tables.dependencies import TableServiceDep
from mpcontribs_api.domains.tables.models import Table, TableFilter, TableIn, TableOut, TablePatch
from mpcontribs_api.pagination import CursorParams

router = APIRouter()


@router.get("")
async def read_many(
    service: TableServiceDep,
    pagination: Annotated[CursorParams, Depends()],
    filter: TableFilter = FilterDepends(TableFilter),
    fields: FieldSelector = None,
):
    selected = TableOut.parse_fields(fields)
    return await service.read_many(filter=filter, fields=selected, pagination=pagination)


@router.get("/item")
async def read_one_by_identity(
    service: TableServiceDep,
    identity: Annotated[ComponentIdentity, Depends()],
    fields: FieldSelector = None,
):
    """Return a single table addressed by its content ``md5`` (its natural key)."""
    selected = TableOut.parse_fields(fields)
    return await service.read_one(identifiers=identity.as_dict(), fields=selected)


@router.delete("/item", response_model=ComponentDeleteResponse, dependencies=[Depends(require_user)])
async def delete_one_by_identity(service: TableServiceDep, identity: Annotated[ComponentIdentity, Depends()]):
    """Delete a single table addressed by its content ``md5`` (its natural key)."""
    return await service.delete_one(identifiers=identity.as_dict())


@router.patch("/item", dependencies=[Depends(require_user)])
async def update_one_by_identity(
    service: TableServiceDep,
    identity: Annotated[ComponentIdentity, Depends()],
    update: TablePatch,
):
    """Patch a single table addressed by its content ``md5`` (its natural key)."""
    return await service.update_one(identifiers=identity.as_dict(), update=update)


@router.get("/{id}")
async def read_one(
    service: TableServiceDep,
    id: str,
    fields: FieldSelector = None,
):
    """Return a single table addressed by its ``_id``."""
    selected = TableOut.parse_fields(fields)
    return await service.read_one(identifiers={"id": id}, fields=selected)


@router.post("/download", dependencies=[Depends(require_user)])
async def download_table(
    service: TableServiceDep,
    filter: TableFilter = FilterDepends(TableFilter),
    format: DownloadFormat = DownloadFormat.JSONL,
):
    """Enqueue an async export of the matching tables, returning the download job ticket."""
    return await service.queue_download(filter=filter, format=format)


@router.post("", response_model=BulkWriteSummary[Table], dependencies=[Depends(require_writer)])
async def insert_many(
    service: TableServiceDep,
    tables: list[TableIn],
):
    return await service.insert_many(components=tables)


@router.delete("", response_model=ComponentDeleteResponse, dependencies=[Depends(require_user)])
async def delete_many(service: TableServiceDep, filter: TableFilter = FilterDepends(TableFilter)):
    return await service.delete_many(filter=filter)


@router.delete("/{id}", response_model=ComponentDeleteResponse, dependencies=[Depends(require_user)])
async def delete_one(service: TableServiceDep, id: str):
    """Delete a single table addressed by its ``_id``"""
    return await service.delete_one(identifiers={"id": id})


@router.patch("/{id}", dependencies=[Depends(require_user)])
async def update_one(
    service: TableServiceDep,
    id: str,
    update: TablePatch,
):
    """Patch a single table addressed by its ``_id``."""
    return await service.update_one(identifiers={"id": id}, update=update)
