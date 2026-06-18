from beanie import PydanticObjectId
from fastapi_filter.contrib.beanie import Filter
from pydantic import field_validator

from mpcontribs_api.domains._shared.models import Component, ComponentIn, DocumentOut
from mpcontribs_api.domains._shared.types import FileLike, MD5Hash, MimeFormat
from mpcontribs_api.exceptions import ValidationError
from mpcontribs_api.projection import SparseFieldsModel

ACCEPTED_FORMATS = ["jpg", "jpeg", "png", "csv", "parquet", "gz"]


def _validate_attachment_name(v: str) -> str:
    parts = v.strip().split(".")
    if parts[-1].lower() not in ACCEPTED_FORMATS:
        raise ValidationError(
            f"Attachment extension not in allowed formats: {ACCEPTED_FORMATS}",
            found_extension=parts[-1],
        )
    return v


class Attachment(Component):
    hash_fields = frozenset({"mime", "content"})
    mime: MimeFormat
    content: int

    class Settings:
        name = "attachments"

    @field_validator("name", mode="before")
    @classmethod
    def _name_with_extension(cls, v: str) -> str:
        return _validate_attachment_name(v)


class AttachmentIn(ComponentIn):
    """User-supplied attachment content. ``_id`` and ``md5`` are server-assigned, so absent here."""

    mime: MimeFormat
    content: int

    @field_validator("name", mode="before")
    @classmethod
    def _name_with_extension(cls, v: str) -> str:
        return _validate_attachment_name(v)


class AttachmentOut(DocumentOut[PydanticObjectId]):
    name: FileLike | None = None
    md5: MD5Hash | None = None
    mime: MimeFormat | None = None
    content: int | None = None

    @staticmethod
    def default_fields() -> list[str]:
        # Light default; content fetched via ?_fields=.
        return ["id", "name", "md5", "mime"]


class AttachmentPatch(SparseFieldsModel):
    name: FileLike | None = None
    mime: MimeFormat | None = None
    content: int | None = None


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

    # sorting
    order_by: list[str] | None = None

    class Constants(Filter.Constants):
        model = Attachment
