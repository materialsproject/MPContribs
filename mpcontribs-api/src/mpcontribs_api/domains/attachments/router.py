from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from fastapi_filter import FilterDepends

from mpcontribs_api.dependencies import S3Dep, require_user
from mpcontribs_api.domains._shared.models import ComponentDeleteResponse
from mpcontribs_api.domains._shared.types import (
    DownloadFormat,
    FieldSelector,
    MD5Hash,
    ShortMimeFormat,
    download_filename,
)
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
async def read_one_by_md5(
    service: AttachmentServiceDep,
    md5: MD5Hash,
    fields: FieldSelector = None,
):
    """Return a single attachment addressed by its content ``md5`` (its natural key)."""
    selected = AttachmentOut.parse_fields(fields)
    return await service.read_one(identifiers={"md5": md5}, fields=selected)


@router.delete("/item", response_model=ComponentDeleteResponse, dependencies=[Depends(require_user)])
async def delete_one_by_md5(service: AttachmentServiceDep, md5: MD5Hash):
    """Delete a single attachment addressed by its content ``md5`` (its natural key)."""
    return await service.delete_one(identifiers={"md5": md5})


@router.patch("/item", dependencies=[Depends(require_user)])
async def update_one_by_md5(
    service: AttachmentServiceDep,
    md5: MD5Hash,
    update: AttachmentPatch,
):
    """Patch a single attachment addressed by its content ``md5`` (its natural key)."""
    return await service.update_one(identifiers={"md5": md5}, update=update)


@router.get("/{id}")
async def read_one(
    service: AttachmentServiceDep,
    id: str,
    fields: FieldSelector = None,
):
    """Return a single attachment addressed by its ``_id``."""
    selected = AttachmentOut.parse_fields(fields)
    return await service.read_one(identifiers={"id": id}, fields=selected)


@router.get("/download/{short_mime}")
async def download_attachment(
    service: AttachmentServiceDep,
    format: DownloadFormat,
    s3: S3Dep,
    short_mime: ShortMimeFormat = ShortMimeFormat.GZ,
    ignore_cache: bool = False,
    filter: AttachmentFilter = FilterDepends(AttachmentFilter),
    fields: FieldSelector = None,
) -> StreamingResponse:
    selected = AttachmentOut.parse_fields(fields)
    body = await service.download(
        format=format,
        short_mime=short_mime,
        ignore_cache=ignore_cache,
        filter=filter,
        fields=selected,
        s3=s3,
    )
    filename = download_filename("attachments", format, short_mime)
    return StreamingResponse(
        body,
        media_type="application/gzip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
