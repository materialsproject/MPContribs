from typing import Annotated

from fastapi import Depends

from mpcontribs_api.dependencies import UserDep
from mpcontribs_api.domains.downloads.repository import MongoDbDownloadRepository
from mpcontribs_api.domains.downloads.service import DownloadService


def get_download_service(user: UserDep) -> DownloadService:
    return DownloadService(downloads=MongoDbDownloadRepository(user))


DownloadServiceDep = Annotated[DownloadService, Depends(get_download_service)]
