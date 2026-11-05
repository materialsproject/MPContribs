from typing import Annotated, Any, ClassVar, Self

from beanie import Document, PydanticObjectId
from pydantic import BaseModel, ConfigDict, Field
from pymongo.results import DeleteResult as MongoDeleteResult

from mpcontribs_api import pagination
from mpcontribs_api.domains._shared.types import Identity
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

    HAS_DERIVED_FIELDS: ClassVar[bool] = False
    # The domain's ``Identity`` subclass. Describes how documents are uniquely addressed
    identity_model: ClassVar[type[Identity]] = Identity
    # Required, non-null, resource-specific id. Overrides Document's optional ``PydanticObjectId`` id.
    id: TId = Field(alias="_id")  # pyright: ignore[reportGeneralTypeIssues, reportIncompatibleVariableOverride]

    def identifiers(self) -> dict[str, Any]:
        """This document's natural-key field values, keyed by ``identity_model.model_fields``.

        The natural/unique key is a caller-suppliable alternative to the Mongo ``_id`` (e.g.
        ``{"name", "owner"}`` for a project group); it comes straight from the domain's ``Identity``
        subclass so each domain declares its key exactly once.
        """
        return {field: getattr(self, field) for field in self.identity_model.model_fields}

    def identity(self) -> Identity:
        """This document's identity as a concrete :class:`Identity`, built from its own fields."""
        return self.identity_model.from_document(
            {name: getattr(self, name) for name in self.identity_model.model_fields}
        )

    def derived_field_updates(self) -> dict[str, Any]:
        """Server-derived fields to persist alongside a patch.

        Called by the repository on a copy of this document that already has the patch applied
        in memory; the returned mapping is merged into the same ``$set`` write. Default: none.
        """
        return {}

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
    are declared once here for the repository to read off any resource's output model."""

    # lets POST/PUT responses correctly bring ``_id`` into ``id``, without it ``id`` ends up as None
    model_config = ConfigDict(populate_by_name=True)

    id: Annotated[TId | None, Field(alias="_id", serialization_alias="id")] = None


class DeleteResult(BaseModel):
    """Uniform result of any delete across every domain.

    ``num_deleted`` counts the documents actually removed.
    ``num_children_deleted`` counts cascade-deleted children.
    ``referenced_ids`` are component ids skipped because a contribution still references them.
    ``num_skipped`` is the count of 'referenced_ids'.
    """

    num_deleted: int
    num_children_deleted: int = 0
    num_skipped: int = 0
    referenced_ids: list[PydanticObjectId] = Field(default_factory=list)

    @classmethod
    def from_delete_result(cls, delete_result: MongoDeleteResult) -> Self:
        return cls(num_deleted=delete_result.deleted_count)
