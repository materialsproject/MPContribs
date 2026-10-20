from typing import Annotated

from fastapi import Depends

from mpcontribs_api.dependencies import S3Dep, SQSDep, UserDep
from mpcontribs_api.domains.uploads.repository import MongoDbUploadRepository
from mpcontribs_api.domains.uploads.service import UploadService


def get_upload_service(user: UserDep, s3: S3Dep, sqs: SQSDep) -> UploadService:
    return UploadService(
        user=user,
        uploads=MongoDbUploadRepository(user),
        s3=s3,
        sqs=sqs,
    )


UploadServiceDep = Annotated[UploadService, Depends(get_upload_service)]
