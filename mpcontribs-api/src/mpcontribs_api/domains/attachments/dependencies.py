from typing import Annotated

from fastapi import Depends

from mpcontribs_api.dependencies import UserDep
from mpcontribs_api.domains.attachments.models import AttachmentFilter, AttachmentOut
from mpcontribs_api.domains.attachments.repository import MongoDbAttachmentRepository
from mpcontribs_api.domains.components.service import ComponentService
from mpcontribs_api.domains.contributions.repository import MongoDbContributionRepository

AttachmentService = ComponentService[AttachmentOut, AttachmentFilter]


def get_attachment_service(user: UserDep) -> AttachmentService:
    return ComponentService(
        MongoDbAttachmentRepository(user),
        MongoDbContributionRepository(user),
        subtype="attachment",
        ref_field="attachments",
    )


AttachmentServiceDep = Annotated[AttachmentService, Depends(get_attachment_service)]
