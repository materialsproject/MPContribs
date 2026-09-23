from typing import Annotated

from fastapi import Depends

from mpcontribs_api.dependencies import UserDep
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
from mpcontribs_api.domains.downloads.dependencies import DownloadServiceDep

AttachmentService = ComponentService[Attachment, AttachmentIn, AttachmentOut, AttachmentFilter, AttachmentPatch]


def get_attachment_service(user: UserDep, downloads: DownloadServiceDep) -> AttachmentService:
    return ComponentService(
        MongoDbAttachmentRepository(user),
        MongoDbContributionRepository(user),
        user=user,
        downloads=downloads,
        ref_field="attachments",
    )


AttachmentServiceDep = Annotated[AttachmentService, Depends(get_attachment_service)]
