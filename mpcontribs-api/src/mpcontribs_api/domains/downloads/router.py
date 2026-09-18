from fastapi import APIRouter

from mpcontribs_api.dependencies import UserDep
from mpcontribs_api.domains._shared.types import FieldSelector
from mpcontribs_api.domains.downloads.dependencies import DownloadServiceDep
from mpcontribs_api.domains.downloads.models import DownloadOut

router = APIRouter()


@router.get("/{s3_key}")
async def read_one(
    service: DownloadServiceDep,
    user: UserDep,
    s3_key: str,
    fields: FieldSelector = None,
) -> DownloadOut | None:
    selected = DownloadOut.parse_fields(fields)
    return await service.read_one(user=user, s3_key=s3_key, fields=selected)


@router.get(path="{s3_key}/content")
async def get_presigned_url(
    service: DownloadServiceDep,
    user: UserDep,
    s3_key: str,
) -> str:
    return await service.get_presigned_url(user=user, s3_key=s3_key)
