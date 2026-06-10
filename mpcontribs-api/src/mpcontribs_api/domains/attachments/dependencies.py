from typing import Annotated

from fastapi import Depends

from mpcontribs_api.dependencies import UserDep
from mpcontribs_api.domains.attachments.repository import MongoDbAttachmentRepository


def get_scoped_attachments(user: UserDep) -> MongoDbAttachmentRepository:
    return MongoDbAttachmentRepository(user)


AttachmentDep = Annotated[MongoDbAttachmentRepository, Depends(get_scoped_attachments)]
