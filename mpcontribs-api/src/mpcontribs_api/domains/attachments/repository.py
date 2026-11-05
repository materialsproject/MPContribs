from mpcontribs_api.domains.attachments.models import Attachment, AttachmentFilter, AttachmentOut
from mpcontribs_api.domains.components.repository import MongoDbComponentsRepository


class MongoDbAttachmentRepository(MongoDbComponentsRepository[Attachment, AttachmentOut, AttachmentFilter]):
    """Repository for the thin, content-addressed attachment index.

    All behavior (reads, cascade delete, empty read scope) comes from
    :class:`MongoDbComponentsRepository`; this subclass only binds the collection.
    """

    document_model = Attachment
    out_model = AttachmentOut
