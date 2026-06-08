from typing import Any

from pymongo.asynchronous.client_session import AsyncClientSession

from mpcontribs_api.auth import User
from mpcontribs_api.config import get_settings
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

    async def insert_attachments(
        self,
        attachments: list[AttachmentIn],
        session: AsyncClientSession | None = None,
    ) -> list[Attachment]:
        """Bulk-insert attachments, chunked to fit within a transaction's payload budget.

        Args:
            attachments: attachments to insert
            session: optional client session; pass when inserting inside a transaction
        """
        if not attachments:
            return []
        docs = [Attachment.model_validate(a.model_dump()) for a in attachments]
        chunk_size = get_settings().mongo.component_insert_chunk_size
        for start in range(0, len(docs), chunk_size):
            await Attachment.insert_many(docs[start : start + chunk_size], ordered=False, session=session)
        return docs
