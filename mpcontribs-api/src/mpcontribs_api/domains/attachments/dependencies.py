from typing import Annotated

from fastapi import Depends

from mpcontribs_api.dependencies import S3Dep, SQSDep, UserDep
from mpcontribs_api.domains._shared.service import ComponentService
from mpcontribs_api.domains.attachments.models import (
    Attachment,
    AttachmentFilter,
    AttachmentIn,
    AttachmentOut,
    AttachmentPatch,
)
from mpcontribs_api.domains.attachments.repository import MongoDbAttachmentRepository
from mpcontribs_api.domains.contributions.repository import MongoDbContributionRepository
from mpcontribs_api.domains.downloads.service import DownloadService

AttachmentService = ComponentService[Attachment, AttachmentIn, AttachmentOut, AttachmentFilter, AttachmentPatch]


def get_attachment_service(user: UserDep, sqs: SQSDep, s3: S3Dep) -> AttachmentService:
    return ComponentService(
        MongoDbAttachmentRepository(user),
        MongoDbContributionRepository(user),
        user=user,
        downloads=DownloadService(user, sqs=sqs, s3=s3),
        ref_field="attachments",
    )


AttachmentServiceDep = Annotated[AttachmentService, Depends(get_attachment_service)]
