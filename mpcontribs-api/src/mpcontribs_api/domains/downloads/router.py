from beanie import PydanticObjectId
from fastapi import APIRouter, Depends

from mpcontribs_api.dependencies import require_user
from mpcontribs_api.domains._shared.types import FieldSelector
from mpcontribs_api.domains.downloads.dependencies import DownloadServiceDep
from mpcontribs_api.domains.downloads.models import DownloadOut

router = APIRouter()


@router.get("/{id}", dependencies=[Depends(require_user)])
async def read_one(
    service: DownloadServiceDep,
    id: PydanticObjectId,
    fields: FieldSelector = None,
) -> DownloadOut | None:
    selected = DownloadOut.parse_fields(fields)
    return await service.read_one(download_id=id, fields=selected)


@router.get("/{id}/content", dependencies=[Depends(require_user)])
async def get_presigned_url(
    service: DownloadServiceDep,
    id: PydanticObjectId,
) -> str:
    return await service.get_presigned_url(download_id=id)
