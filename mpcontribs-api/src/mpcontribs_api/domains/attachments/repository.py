from mpcontribs_api.domains._shared.components import MongoDbComponentsRepository
from mpcontribs_api.domains.attachments.models import (
    Attachment,
    AttachmentFilter,
    AttachmentIn,
    AttachmentOut,
    AttachmentPatch,
)


class MongoDbAttachmentRepository(
    MongoDbComponentsRepository[Attachment, AttachmentIn, AttachmentOut, AttachmentFilter, AttachmentPatch]
):
    document_model = Attachment
    out_model = AttachmentOut
