from mpcontribs_api.domains._shared.service import ComponentService
from mpcontribs_api.domains.attachments.models import AttachmentFilter
from mpcontribs_api.domains.attachments.repository import MongoDbAttachmentRepository


class AttachmentService(ComponentService[MongoDbAttachmentRepository, AttachmentFilter]):
    """Defines which field on a Contribtution to look in for the references."""

    ref_field = "attachments"
