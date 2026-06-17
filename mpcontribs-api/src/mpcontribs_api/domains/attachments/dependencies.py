from typing import Annotated

from fastapi import Depends

from mpcontribs_api.dependencies import UserDep
from mpcontribs_api.domains.attachments.repository import MongoDbAttachmentRepository
from mpcontribs_api.domains.attachments.service import AttachmentService
from mpcontribs_api.domains.contributions.repository import MongoDbContributionRepository


def get_scoped_attachments(user: UserDep) -> MongoDbAttachmentRepository:
    return MongoDbAttachmentRepository(user)


AttachmentDep = Annotated[MongoDbAttachmentRepository, Depends(get_scoped_attachments)]


def get_attachment_service(user: UserDep) -> AttachmentService:
    return AttachmentService(MongoDbAttachmentRepository(user), MongoDbContributionRepository(user))


AttachmentServiceDep = Annotated[AttachmentService, Depends(get_attachment_service)]
