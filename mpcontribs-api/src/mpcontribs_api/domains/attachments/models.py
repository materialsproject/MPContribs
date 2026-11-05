from beanie import PydanticObjectId
from pydantic import BaseModel
from pymongo import ASCENDING, IndexModel

from mpcontribs_api.domains._shared.filters import BaseFilter
from mpcontribs_api.domains._shared.types import MimeFormat, NFKCStr, Sha256Hash, ShortStr
from mpcontribs_api.domains.components.models import Component, ComponentIdentity, ComponentOut


class Attachment(Component):
    """Thin index record locating one content-addressed S3 attachment object.

    The attachment content lives in S3 at ``mpcontribs/{project}/components/attachments/{hash}.{ext}``;
    this record is a self-contained locator plus the MIME type clients filter on.
    """

    # Content type of the stored object, for display/filtering.
    mime: MimeFormat

    class Settings:
        name = "attachments"
        indexes = [
            # Deployed index names are kept stable — renaming forces a drop/recreate.
            ComponentIdentity.index_model(name="identity", unique=True),
            IndexModel(keys=[("size", ASCENDING)], name="size"),
        ]


class AttachmentIn(BaseModel):
    """A by-name reference to an attachment from a contribution row.

    Not a component write model — components are worker-created in S3 and never inserted via the API.
    A contribution row names its attachments; the worker resolves each name to the content-addressed
    object and links it. Mirrors :class:`StructureIn`/:class:`TableIn`.
    """

    # NFKC-normalized so compatibility-equivalent spellings of a name collapse to one stored form.
    name: NFKCStr


class AttachmentOut(ComponentOut):
    """Attachment metadata served from Mongo. Content is served separately from S3 (presigned GET)."""

    mime: MimeFormat | None = None

    @staticmethod
    def default_fields() -> tuple[str, ...]:
        return ("id", "project", "hash", "size", "ext", "mime")


class AttachmentFilter(BaseFilter):
    id: PydanticObjectId | None = None
    id__in: list[PydanticObjectId] | None = None
    id__neq: PydanticObjectId | None = None

    project: ShortStr | None = None
    project__in: list[ShortStr] | None = None

    hash: Sha256Hash | None = None
    hash__in: list[Sha256Hash] | None = None
    hash__neq: Sha256Hash | None = None

    size: int | None = None
    size__gte: int | None = None
    size__lte: int | None = None

    mime: MimeFormat | None = None
    mime__in: list[MimeFormat] | None = None
    mime__neq: MimeFormat | None = None
    mime__ilike: MimeFormat | None = None

    # sorting
    order_by: list[str] | None = None

    class Constants(BaseFilter.Constants):
        model = Attachment
