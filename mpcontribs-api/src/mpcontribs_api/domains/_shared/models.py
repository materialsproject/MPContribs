import hashlib
import json
import unicodedata
from collections.abc import Mapping
from typing import Annotated, Any, ClassVar, Self

from beanie import DocumentWithSoftDelete, PydanticObjectId
from pydantic import BaseModel, Field
from pymongo.results import DeleteResult

from mpcontribs_api import pagination
from mpcontribs_api.domains._shared.types import MD5Hash
from mpcontribs_api.projection import SparseFieldsModel


class BaseDocumentWithInput[TId](DocumentWithSoftDelete):
    """A stored resource document with a required ``id`` and an input counterpart.

    Subclasses bind their id type as ``TId``. The ``id`` is declared here as required and non-null so
    the repository can always read and key on it, while ``TId`` lets each resource pick its own id
    type (``ShortStr`` for projects, ``PydanticObjectId`` for contributions). ``from_input_model``
    translates a validated input payload into a full document; the base param is intentionally ``Any``
    so each resource's override can declare its concrete input model without violating LSP (input
    models subclass their document, so they can't be bound as a class type parameter). Soft-delete
    behavior is inherited from ``DocumentWithSoftDelete``.
    """

    # Required, non-null, resource-specific id. Overrides Document's optional ``PydanticObjectId`` id.
    id: TId = Field(alias="_id")  # pyright: ignore[reportGeneralTypeIssues, reportIncompatibleVariableOverride]

    @classmethod
    def from_input_model(cls, data: Any) -> Self:
        """Translate a validated input payload into a full stored document."""
        return cls(**data.model_dump())

    @staticmethod
    def decode_cursor(cursor: str) -> str | PydanticObjectId:
        """Decodes the cursor the an ObjectId"""
        return PydanticObjectId(pagination.decode_cursor(cursor=cursor))


class DocumentOut[TId](SparseFieldsModel):
    """Base output model for resources addressed by an ``_id``.

    Mirrors :class:`BaseDocumentWithInput`: subclasses bind their id type as ``TId`` so each resource
    owns its id type, while the field (optional, since projections may omit it) and its alias wiring
    are declared once here for the repository to read off any resource's output model.
    """

    id: Annotated[TId | None, Field(alias="_id", serialization_alias="id")] = None


class DeleteResponse(BaseModel):
    num_deleted: int

    @classmethod
    def from_delete_result(cls, delete_result: DeleteResult) -> Self:
        return cls(num_deleted=delete_result.deleted_count)


def canonical_md5(payload: Mapping[str, Any]) -> str:
    """MD5 hex digest of a content mapping, stable across processes/hosts."""
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    normalized = unicodedata.normalize("NFC", text)
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()


class Component(BaseDocumentWithInput[PydanticObjectId]):
    name: str
    md5: MD5Hash

    hash_fields: ClassVar[frozenset[str]]

    def compute_md5(self) -> str:
        payload = self.model_dump(mode="json", include=set(self.hash_fields), by_alias=False)
        return canonical_md5(payload)
