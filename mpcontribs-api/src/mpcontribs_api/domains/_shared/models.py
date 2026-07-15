import hashlib
import json
import unicodedata
from collections.abc import Mapping
from typing import Annotated, Any, ClassVar, Self

from beanie import Document, PydanticObjectId
from pydantic import BaseModel, Field, model_validator
from pymongo.results import DeleteResult

from mpcontribs_api import pagination
from mpcontribs_api.domains._shared.types import MD5Hash
from mpcontribs_api.projection import SparseFieldsModel


class BaseDocumentWithInput[TId](Document):
    """A stored resource document with a required ``id`` and an input counterpart.

    Subclasses bind their id type as ``TId``. The ``id`` is declared here as required and non-null so
    the repository can always read and key on it, while ``TId`` lets each resource pick its own id
    type (``ShortStr`` for projects, ``PydanticObjectId`` for contributions). ``from_input_model``
    translates a validated input payload into a full document; the base param is intentionally ``Any``
    so each resource's override can declare its concrete input model without violating LSP (input
    models subclass their document, so they can't be bound as a class type parameter).
    """

    # Required, non-null, resource-specific id. Overrides Document's optional ``PydanticObjectId`` id.
    id: TId = Field(alias="_id")  # pyright: ignore[reportGeneralTypeIssues, reportIncompatibleVariableOverride]

    @classmethod
    def identifier_fields(cls) -> frozenset[str]:
        """Field names that uniquely identify a document in this collection.

        This is the natural/unique key a caller can supply without first knowing the Mongo ``_id``
        (e.g. ``{"name", "owner"}`` for a project group). The repository pairs these names with
        caller-supplied values to locate a single resource, and rejects any value dict whose keys
        don't match this set. Defaults to the primary key; subclasses with a meaningful compound key
        override it.
        """
        return frozenset({"id"})

    def identifiers(self) -> dict[str, Any]:
        """This document's identifier field values, keyed by :meth:`identifier_fields`."""
        return {field: getattr(self, field) for field in self.identifier_fields()}

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


class ComponentDeleteResponse(DeleteResponse):
    """Result of a component delete that may leave referenced components in place.

    ``num_deleted`` (inherited) counts components actually removed; ``referenced_ids`` are the
    component ids skipped because a contribution still references them, and ``num_skipped`` is
    their count.
    """

    referenced_ids: list[PydanticObjectId] = Field(default_factory=list)
    num_skipped: int = 0


def canonical_md5(payload: Mapping[str, Any]) -> str:
    """MD5 hex digest of a content mapping, stable across processes/hosts."""
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    normalized = unicodedata.normalize("NFC", text)
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()


class ComponentIn(BaseModel):
    """Base for component input payloads.

    Components are content-addressed: the server computes ``md5`` from the content and assigns the
    ``_id`` on insert, so neither is part of the input contract. Subclasses add the required content
    fields for their resource.
    """

    name: str


class Component(BaseDocumentWithInput[PydanticObjectId]):
    """Stored component document.

    ``md5`` is server-authoritative: it is (re)computed from ``hash_fields`` whenever a full document
    is validated — on insert, on update, and on full-document reads — so a client-supplied value can
    never define a component's content identity.
    """

    name: str
    # Server-computed; the placeholder default is overwritten by ``_recompute_md5`` on validation.
    md5: MD5Hash = Field(default="0" * 32)

    hash_fields: ClassVar[frozenset[str]]

    # The md5 functions look redundant but aren't, we should keep both
    # Used in patching to compute the hash after an update - should not return self
    def compute_md5(self) -> str:
        payload = self.model_dump(mode="json", include=set(self.hash_fields), by_alias=False)
        return canonical_md5(payload)

    # Used on validation - must return self
    @model_validator(mode="after")
    def _recompute_md5(self) -> Self:
        self.md5 = self.compute_md5()
        return self

    @classmethod
    def from_input(cls, input: ComponentIn) -> Self:
        """Build a stored document from an input payload, assigning a fresh id (md5 is computed).

        The default maps every input field onto the document one-to-one. Subclasses whose document
        carries fields that are absent from the input or derived from it should override this - see
        ``Table.from_input``, which computes ``total_data_rows`` from the data frame.
        """
        payload = input.model_dump()
        payload["_id"] = PydanticObjectId()
        return cls.model_validate(payload)
