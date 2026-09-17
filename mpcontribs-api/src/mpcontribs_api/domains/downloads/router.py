from fastapi import APIRouter

from mpcontribs_api.domains.downloads.dependencies import DownloadServiceDep
from mpcontribs_api.domains.downloads.models import DownloadOut

router = APIRouter()


@router.get("/{s3_key}")
async def read_one(
    service: DownloadServiceDep,
    s3_key: str,
) -> DownloadOut:
    return await service.read_one(s3_key=s3_key)


@router.get(path="{s3_key}/content")
async def get_presigned_url(
    service: DownloadServiceDep,
    s3_key: str,
) -> str:
    return await service.get_presigned_url(s3_key=s3_key)
