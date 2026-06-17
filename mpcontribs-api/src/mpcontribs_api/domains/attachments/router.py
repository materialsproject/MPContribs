from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from fastapi_filter import FilterDepends

from mpcontribs_api.dependencies import S3Dep
from mpcontribs_api.domains._shared.models import ComponentDeleteResponse
from mpcontribs_api.domains._shared.types import (
    DownloadFormat,
    FieldSelector,
    ShortMimeFormat,
    download_filename,
)
from mpcontribs_api.domains.attachments.dependencies import AttachmentServiceDep
from mpcontribs_api.domains.attachments.models import AttachmentFilter, AttachmentOut
from mpcontribs_api.pagination import CursorParams, Page

router = APIRouter()


@router.get("", response_model=Page[AttachmentOut])
async def get_attachments(
    service: AttachmentServiceDep,
    pagination: Annotated[CursorParams, Depends()],
    filter: AttachmentFilter = FilterDepends(AttachmentFilter),
    fields: FieldSelector = AttachmentOut.default_fields(),
):
    selected = AttachmentOut.parse_fields(fields)
    return await service.get_many(filter=filter, fields=selected, pagination=pagination)


@router.get("/{pk}", response_model=AttachmentOut)
async def get_attachment(
    service: AttachmentServiceDep,
    pk: str,
    fields: FieldSelector = AttachmentOut.default_fields(),
):
    selected = AttachmentOut.parse_fields(fields)
    return await service.get_by_id(id=pk, fields=selected)


@router.get("/download/{short_mime}")
async def download_attachment(
    service: AttachmentServiceDep,
    format: DownloadFormat,
    s3: S3Dep,
    short_mime: ShortMimeFormat = ShortMimeFormat.GZ,
    ignore_cache: bool = False,
    filter: AttachmentFilter = FilterDepends(AttachmentFilter),
    fields: FieldSelector = AttachmentOut.default_fields(),
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


@router.delete("", response_model=ComponentDeleteResponse)
async def delete_attachments(service: AttachmentServiceDep, filter: AttachmentFilter = FilterDepends(AttachmentFilter)):
    return await service.delete(filter=filter)


@router.delete("/{id}", response_model=ComponentDeleteResponse)
async def delete_attachment_by_id(service: AttachmentServiceDep, id: str):
    return await service.delete_by_id(id=id)
