from typing import Any

from mpcontribs_api.auth import User
from mpcontribs_api.domains._shared.repository import MongoDbRepository
from mpcontribs_api.domains.attachments.models import (
    Attachment,
    AttachmentFilter,
    AttachmentIn,
    AttachmentOut,
    AttachmentPatch,
)


class MongoDbAttachmentRepository(
    MongoDbRepository[Attachment, AttachmentIn, AttachmentOut, AttachmentFilter, AttachmentPatch]
):
    document_model = Attachment
    out_model = AttachmentOut

    @staticmethod
    def _build_scope(user: User) -> dict[str, Any]:
        return {}

    async def insert_attachments(self, attachments: list[AttachmentIn]) -> list[Attachment]:
        if not attachments:
            return []
        docs = [Attachment.model_validate(a.model_dump()) for a in attachments]
        await Attachment.insert_many(docs, ordered=False)
        return docs
