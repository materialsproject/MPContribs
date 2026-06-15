from typing import Annotated

from fastapi import APIRouter, Depends, Response
from fastapi.responses import StreamingResponse
from fastapi_filter import FilterDepends

from mpcontribs_api.domains._shared.models import DeleteResponse
from mpcontribs_api.domains._shared.types import DownloadFormat, FieldSelector, ShortMimeFormat
from mpcontribs_api.domains.attachments.dependencies import AttachmentDep
from mpcontribs_api.domains.attachments.models import AttachmentFilter, AttachmentOut
from mpcontribs_api.pagination import CursorParams, Page

router = APIRouter()


@router.get("", response_model=Page[AttachmentOut])
async def get_attachments(
    repo: AttachmentDep,
    pagination: Annotated[CursorParams, Depends()],
    filter: AttachmentFilter = FilterDepends(AttachmentFilter),
    fields: FieldSelector = AttachmentOut.default_fields(),
):
    selected = AttachmentOut.parse_fields(fields)
    return await repo.get_attachments(filter=filter, fields=selected, pagination=pagination)


@router.get("/{pk}", response_model=AttachmentOut)
async def get_attachment(
    repo: AttachmentDep,
    pk: str,
    fields: FieldSelector = AttachmentOut.default_fields(),
):
    selected = AttachmentOut.parse_fields(fields)
    return await repo.get_attachment_by_id(id=pk, fields=selected)


@router.get("/download/{short_mime}")
async def download_attachment(
    repo: AttachmentDep,
    response: Response,
    format: DownloadFormat,
    short_mime: ShortMimeFormat = ShortMimeFormat.GZ,
    ignore_cache: bool = False,
    filter: AttachmentFilter = FilterDepends(AttachmentFilter),
    fields: FieldSelector = AttachmentOut.default_fields(),
) -> StreamingResponse:
    selected = AttachmentOut.parse_fields(fields)
    body = await repo.download_attachments(
        format=format,
        short_mime=short_mime,
        ignore_cache=ignore_cache,
        filter=filter,
        fields=selected,
    )
    return StreamingResponse(
        body,
        media_type="application/gzip",
        headers={"Content-Disposition": 'attachment; filename="attachments.jsonl.gz"'},
    )


@router.delete("", response_model=DeleteResponse)
async def delete_attachments(repo: AttachmentDep, filter: AttachmentFilter = FilterDepends(AttachmentFilter)):
    return await repo.delete_attachments(filter=filter)


@router.delete("/{id}", response_model=DeleteResponse)
async def delete_attachment_by_id(repo: AttachmentDep, id: str):
    return await repo.delete_attachment_by_id(id=id)
