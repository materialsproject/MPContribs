from beanie import PydanticObjectId
from fastapi_filter.contrib.beanie import Filter

from mpcontribs_api.domains._shared.models import BaseDocumentWithInput
from mpcontribs_api.types import FileLike, MD5Hash, MimeFormat


class Attachment(BaseDocumentWithInput[PydanticObjectId]):
    name: FileLike
    md5: MD5Hash
    mime: MimeFormat
    content: int

    class Settings:
        name = "attachments"


class AttachmentIn(Attachment):
    pass


class AttachmentFilter(Filter):
    id: PydanticObjectId | None = None
    id__in: list[PydanticObjectId] | None = None
    id__neq: PydanticObjectId | None = None

    md5: MD5Hash | None = None
    md5__in: list[MD5Hash] | None = None
    md5__neq: MD5Hash | None = None

    name: str | None = None
    name__in: list[str] | None = None
    name__neq: str | None = None
    name__ilike: str | None = None

    mime: MimeFormat | None = None
    mime__in: list[MimeFormat] | None = None
    mime__neq: MimeFormat | None = None
    mime__ilike: MimeFormat | None = None

    class Constants(Filter.Constants):
        model = Attachment
