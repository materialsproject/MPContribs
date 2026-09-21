from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi_filter import FilterDepends

from mpcontribs_api.dependencies import require_user
from mpcontribs_api.domains._shared.models import ComponentDeleteResponse, ComponentIdentity
from mpcontribs_api.domains._shared.types import DownloadFormat, FieldSelector
from mpcontribs_api.domains.attachments.dependencies import AttachmentServiceDep
from mpcontribs_api.domains.attachments.models import AttachmentFilter, AttachmentOut, AttachmentPatch
from mpcontribs_api.pagination import CursorParams

router = APIRouter()


@router.get("")
async def read_many(
    service: AttachmentServiceDep,
    pagination: Annotated[CursorParams, Depends()],
    filter: AttachmentFilter = FilterDepends(AttachmentFilter),
    fields: FieldSelector = None,
):
    selected = AttachmentOut.parse_fields(fields)
    return await service.read_many(filter=filter, fields=selected, pagination=pagination)


@router.get("/item")
async def read_one_by_identity(
    service: AttachmentServiceDep,
    identity: Annotated[ComponentIdentity, Depends()],
    fields: FieldSelector = None,
):
    """Return a single attachment addressed by its content ``md5`` (its natural key)."""
    selected = AttachmentOut.parse_fields(fields)
    return await service.read_one(identifiers=identity.as_dict(), fields=selected)


@router.delete("/item", response_model=ComponentDeleteResponse, dependencies=[Depends(require_user)])
async def delete_one_by_identity(service: AttachmentServiceDep, identity: Annotated[ComponentIdentity, Depends()]):
    """Delete a single attachment addressed by its content ``md5`` (its natural key)."""
    return await service.delete_one(identifiers=identity.as_dict())


@router.patch("/item", dependencies=[Depends(require_user)])
async def update_one_by_identity(
    service: AttachmentServiceDep,
    identity: Annotated[ComponentIdentity, Depends()],
    update: AttachmentPatch,
):
    """Patch a single attachment addressed by its content ``md5`` (its natural key)."""
    return await service.update_one(identifiers=identity.as_dict(), update=update)


@router.get("/{id}")
async def read_one(
    service: AttachmentServiceDep,
    id: str,
    fields: FieldSelector = None,
):
    """Return a single attachment addressed by its ``_id``."""
    selected = AttachmentOut.parse_fields(fields)
    return await service.read_one(identifiers={"id": id}, fields=selected)


@router.post("/download", dependencies=[Depends(require_user)])
async def download_attachment(
    service: AttachmentServiceDep,
    filter: AttachmentFilter = FilterDepends(AttachmentFilter),
    format: DownloadFormat = DownloadFormat.JSONL,
):
    """Enqueue an async export of the matching attachments, returning the download job ticket."""
    return await service.queue_download(filter=filter, format=format)


@router.delete("", response_model=ComponentDeleteResponse, dependencies=[Depends(require_user)])
async def delete_many(service: AttachmentServiceDep, filter: AttachmentFilter = FilterDepends(AttachmentFilter)):
    return await service.delete_many(filter=filter)


@router.delete("/{id}", response_model=ComponentDeleteResponse, dependencies=[Depends(require_user)])
async def delete_one(service: AttachmentServiceDep, id: str):
    """Delete a single attachment addressed by its ``_id``."""
    return await service.delete_one(identifiers={"id": id})


@router.patch("/{id}", dependencies=[Depends(require_user)])
async def update_one(
    service: AttachmentServiceDep,
    id: str,
    update: AttachmentPatch,
):
    """Patch a single attachment addressed by its ``_id``."""
    return await service.update_one(identifiers={"id": id}, update=update)
