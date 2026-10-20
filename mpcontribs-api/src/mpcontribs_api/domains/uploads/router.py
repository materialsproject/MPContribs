from typing import Annotated

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, status
from fastapi_filter import FilterDepends

from mpcontribs_api.dependencies import require_user
from mpcontribs_api.domains._shared.types import FieldSelector
from mpcontribs_api.domains.uploads.dependencies import UploadServiceDep
from mpcontribs_api.domains.uploads.models import (
    CompleteIn,
    GeneratePartsIn,
    PartUrls,
    SessionInitiated,
    UploadCompleted,
    UploadFilter,
    UploadManifest,
    UploadOut,
)
from mpcontribs_api.pagination import CursorParams, Page

# every route requires authentication
router = APIRouter(dependencies=[Depends(dependency=require_user)])


@router.get("", response_model_exclude_unset=True)
async def read_many(
    service: UploadServiceDep,
    pagination: Annotated[CursorParams, Depends()],
    filter: UploadFilter = FilterDepends(UploadFilter),
    fields: FieldSelector = None,
) -> Page[UploadOut]:
    """Search the caller's own upload sessions (filter by operation/project/status), paginated.

    Requires authentication: uploads are private, so reads restricted to the caller's own consumer rather than open.
    """
    selected = UploadOut.parse_fields(fields)
    return await service.read_many(pagination=pagination, filter=filter, fields=selected)


@router.get("/{upload_id}", response_model_exclude_unset=True)
async def read_one(
    service: UploadServiceDep,
    upload_id: PydanticObjectId,
    fields: FieldSelector = None,
) -> UploadOut | None:
    """Return one of the caller's upload sessions by id, or ``null`` when it is not in their scope."""
    selected = UploadOut.parse_fields(fields)
    return await service.read_one(upload_id, fields=selected)


@router.post("", status_code=status.HTTP_201_CREATED)
async def initiate_upload(service: UploadServiceDep, body: UploadManifest) -> SessionInitiated:
    """Create an upload session from a manifest; returns a presigned handle per declared file.

    Each file comes back as a ``FileInitiated`` handle: a single-shot file carries its presigned
    PUT ``url`` directly, while multipart file drives the ``/files/{name}/parts`` and ``/complete`` steps.
    """
    return await service.initiate(manifest=body)


@router.post("/{upload_id}/files/{name}/parts")
async def generate_parts(
    service: UploadServiceDep,
    upload_id: PydanticObjectId,
    name: str,
    body: GeneratePartsIn,
) -> PartUrls:
    """Return presigned URLs to transfer the named file of the session, starting at ``start_part``."""
    return await service.generate_part_urls(upload_id=upload_id, name=name, start_part=body.start_part)


@router.post("/{upload_id}/complete")
async def complete_upload(
    service: UploadServiceDep,
    upload_id: PydanticObjectId,
    body: CompleteIn,
) -> UploadCompleted:
    """Finalize every file in the session (multipart completion with the supplied ETags) and enqueue it."""
    return await service.complete(upload_id=upload_id, files=body.files)
