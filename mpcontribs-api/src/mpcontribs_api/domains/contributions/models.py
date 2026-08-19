from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, ClassVar

from beanie import (
    Insert,
    Link,
    PydanticObjectId,
    Replace,
    Save,
    SaveChanges,
    Update,
    before_event,
)
from bson.errors import InvalidId
from fastapi_filter import FilterDepends, with_prefix
from pydantic import BaseModel, Field, field_validator, model_validator
from pymongo import ASCENDING, IndexModel

from mpcontribs_api._openapi import CONTRIBUTION_DATA_INPUT_DESCRIPTION, CONTRIBUTION_DATA_OUTPUT_DESCRIPTION
from mpcontribs_api.domains._shared.filters import BaseFilter
from mpcontribs_api.domains._shared.models import BaseDocumentWithInput, DocumentOut
from mpcontribs_api.domains._shared.types import ChemicalSystemId, Formula, Identity, MaterialId, Scalar, ShortStr
from mpcontribs_api.domains.attachments.models import Attachment, AttachmentFilter, AttachmentIn
from mpcontribs_api.domains.contributions.data import ContributionData, ContributionPatchData, ContributionStoredData
from mpcontribs_api.domains.structures.models import Structure, StructureFilter, StructureIn
from mpcontribs_api.domains.tables.models import Table, TableFilter, TableIn
from mpcontribs_api.exceptions import ValidationError
from mpcontribs_api.projection import SparseFieldsModel


def _value_at(data: dict[str, Any], path: str) -> Any:
    """Resolve a dotted ``path`` inside ``data``; raises ``KeyError`` if any segment is absent."""
    cursor: Any = data
    for segment in path.split("."):
        if not isinstance(cursor, dict) or segment not in cursor:
            raise KeyError(path)
        cursor = cursor[segment]
    return cursor


def extract_unique_value(data: dict[str, Any] | None, unique_column: str) -> Scalar:
    """Promote the value at a project's ``unique_column`` path to the Contribution's identity value.

    Args:
        data: the contribution's ``data`` payload
        unique_column: the dotted path the project designated as its uniqueness discriminator

    Returns:
        Scalar: the scalar value at ``unique_column``

    Raises:
        ValidationError: if the path is absent or resolves to a non-scalar (dict/list/None)
    """
    try:
        value = _value_at(data or {}, unique_column)
    except KeyError as err:
        raise ValidationError(
            f"unique_column '{unique_column}' is required by the project but missing from Contribution.data",
            unique_column=unique_column,
        ) from err
    if not isinstance(value, Scalar):
        raise ValidationError(
            f"unique_column '{unique_column}' must resolve to a scalar (str/int/float/bool), "
            f"got '{type(value).__name__}'",
            unique_column=unique_column,
        )
    return value


@dataclass(frozen=True, slots=True)
class ContributionIdentity(Identity):
    """The full identity of a Contribution.

    Field declaration order IS the identity/index column order: ``index_model`` and ``projection``
    iterate ``dataclasses.fields`` in that order, so the order is declared exactly once (below).
    """

    # WARNING: the order the fields are specified in reflects their ordering for indices. Changing the order
    # creates index migration. Only change intentionally
    project: str
    material_id: str | None
    chemical_system_id: str
    formula: str | None
    unique_value: Scalar | None = None
    condition_key: str = ""

    # The identifier fields governed by the specificity hierarchy enforced in ``check_hierarchy``
    # (excludes ``project``/``unique_value``/``condition_key``, which don't participate).
    HIERARCHY_FIELDS: ClassVar[frozenset[str]] = frozenset({"material_id", "chemical_system_id", "formula"})

    @staticmethod
    def check_hierarchy(material_id: str | None, chemical_system_id: str | None, formula: str | None) -> None:
        """Enforce the identifier specificity hierarchy ``chemical_system_id`` > ``formula`` > ``material_id."""
        if not chemical_system_id:
            raise ValidationError(
                "chemical_system_id is required (identifier hierarchy: chemical_system_id > formula > material_id)."
            )
        if material_id is not None and formula is None:
            raise ValidationError(
                "formula is required when material_id is specified "
                "(identifier hierarchy: chemical_system_id > formula > material_id).",
                material_id=material_id,
            )


class ContributionBase(BaseModel):
    """Shared fields for Contribution, ContributionIn, and ContributionOut.

    ``data`` uses the annotation-aware ``ContributionData`` validator: raw input may carry the pivot
    grammar (``conductivity (S/cm, T=300K)``, dotted paths) and punctuation folded to ``_`` on write,
    while non-ASCII, empty-after-coercion, and reserved leaf keys are still rejected. The *strict*
    plain-key check (``ContributionStoredData``) is applied only to the coerced, stored
    ``Contribution.data`` (see :class:`Contribution`).
    """

    # Identifiers follow a specificity hierarchy: chemical_system_id > formula > material_id.
    # chemical_system_id is always required
    project: str
    material_id: str | None = None
    chemical_system_id: str
    formula: str | None = None
    is_public: bool = False
    data: ContributionData

    last_modified: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "contributions"
        keep_nulls = False
        indexes = [
            ContributionIdentity.index_model(),
            # Multikey indexes over each Link field's DBRef id so the component-delete
            # reference check (referenced_component_ids) is index-served, not a COLLSCAN.
            IndexModel(keys=[("structures.$id", ASCENDING)], name="ref_structures"),
            IndexModel(keys=[("tables.$id", ASCENDING)], name="ref_tables"),
            IndexModel(keys=[("attachments.$id", ASCENDING)], name="ref_attachments"),
        ]

    @classmethod
    def identifier_fields(cls) -> frozenset[str]:
        """A contribution's natural key is its full :class:`ContributionIdentity` composite."""
        return frozenset({"project", "material_id", "chemical_system_id", "formula", "unique_value", "condition_key"})


class Contribution(ContributionBase, BaseDocumentWithInput[PydanticObjectId]):
    """Models what is actually stored in the database."""

    # Strict validation over stored data rather than coercsion
    data: ContributionStoredData

    # Server owner - uses Project.unique_column to extract the value from Contribution.data
    unique_value: Scalar | None = None
    # Server-owned pivot-condition discriminator; "" until pivoting is wired in (see Identity).
    condition_key: str = ""
    structures: list[Link[Structure]] | None = None
    tables: list[Link[Table]] | None = None
    attachments: list[Link[Attachment]] | None = None

    @classmethod
    def from_input_model(cls, data: ContributionIn) -> Contribution:
        return cls.model_validate(
            {
                **data.model_dump(exclude={"is_public", "structures", "tables", "attachments", "last_modified"}),
                "_id": PydanticObjectId(),
                "is_public": False,
            }
        )

    @before_event(Insert, Replace, Update, Save, SaveChanges)
    def set_last_modified(self):
        self.last_modified = datetime.now(UTC)

    @property
    def identity(self) -> ContributionIdentity:
        """This document's identity, read straight off its own stored fields."""
        return ContributionIdentity(
            project=self.project,
            material_id=self.material_id,
            chemical_system_id=self.chemical_system_id,
            formula=self.formula,
            unique_value=self.unique_value,
            condition_key=self.condition_key,
        )


class ContributionIn(ContributionBase):
    """Fields that users are allowed to submit when adding a Contribution.

    Identifiers follow the specificity hierarchy ``chemical_system_id`` > ``formula`` >
    ``material_id``: ``chemical_system_id`` is always required, and each lower level requires the ones
    above it (see :meth:`_check_identifier_hierarchy`).
    """

    material_id: MaterialId | None = None
    chemical_system_id: ChemicalSystemId
    formula: Formula | None = None
    structures: list[StructureIn] | None = None
    tables: list[TableIn] | None = None
    attachments: list[AttachmentIn] | None = None

    @model_validator(mode="after")
    def _check_identifier_hierarchy(self) -> ContributionIn:
        """Enforce ``chemical_system_id`` > ``formula`` > ``material_id`` (see :meth:`Identity.check_hierarchy`)."""
        ContributionIdentity.check_hierarchy(self.material_id, self.chemical_system_id, self.formula)
        return self

    def has_components(self) -> bool:
        """Returns ``True`` if the contribution has any components (structures, tables, attachments)"""
        return bool(self.structures or self.tables or self.attachments)

    def component_count(self) -> int:
        """Returns the total number of components (structures, tables, attachments) in the contribution"""
        return len(self.structures or []) + len(self.tables or []) + len(self.attachments or [])

    def identity(self, unique_value: Scalar | None = None, condition_key: str = "") -> ContributionIdentity:
        """Build this contribution's :class:`ContributionIdentity` from its flat fields plus server-resolved parts.

        ``unique_value`` and ``condition_key`` are server-resolved, so they are passed in rather than
        read off the (untrusted) input model.
        """
        return ContributionIdentity(
            project=self.project,
            material_id=self.material_id,
            chemical_system_id=self.chemical_system_id,
            formula=self.formula,
            unique_value=unique_value,
            condition_key=condition_key,
        )

    def identity_dict(self, unique_value: Scalar | None = None, condition_key: str = "") -> dict[str, Any]:
        """Returns the identity fields of a contribution (outside of id) for reporting and upsert."""
        return self.identity(unique_value, condition_key).as_dict()


class ContributionOut(DocumentOut[PydanticObjectId]):
    project: str | None = None
    material_id: str | None = None
    chemical_system_id: str | None = None
    formula: str | None = None
    unique_value: Scalar | None = None
    condition_key: str | None = None
    is_public: bool | None = None
    last_modified: datetime | None = None
    # No input validators on the read path: stored documents are trusted, and re-validating here
    # would 500 on historical data that missed the correction (see carrier_transport contribs)
    data: dict[str, Any] | None = Field(default=None, description=CONTRIBUTION_DATA_OUTPUT_DESCRIPTION)
    structures: list[Link[Structure]] | None = None
    tables: list[Link[Table]] | None = None
    attachments: list[Link[Attachment]] | None = None

    @staticmethod
    def default_fields() -> tuple[str, ...]:
        return (
            "id",
            "project",
            "material_id",
            "chemical_system_id",
            "formula",
            "unique_value",
            "is_public",
            "last_modified",
        )


class ContributionPatch(SparseFieldsModel):
    """Fields that can be specified for partial updates to a Contribution."""

    project: str | None = None
    material_id: MaterialId | None = None
    chemical_system_id: ChemicalSystemId | None = None
    formula: Formula | None = None
    is_public: bool | None = None
    # Permissive validator: a merge patch may address a single field inside a stored quantity leaf
    # (e.g. ``{"bandgap": {"unit": "kg"}}``). replace_data=True re-validates strictly in the service.
    data: ContributionPatchData = Field(default=None, description=CONTRIBUTION_DATA_INPUT_DESCRIPTION)
    structures: list[Link[Structure]] | None = None
    tables: list[Link[Table]] | None = None
    attachments: list[Link[Attachment]] | None = None


class ContributionFilter(BaseFilter):
    id: PydanticObjectId | None = None
    id__in: list[PydanticObjectId] | None = None
    id__neq: PydanticObjectId | None = None

    project: str | None = None
    project__in: list[ShortStr] | None = None
    project__neq: str | None = None

    material_id: str | None = None
    material_id__in: list[ShortStr] | None = None
    material_id__neq: ShortStr | None = None
    material_id__ilike: str | None = None

    chemical_system_id: str | None = None
    chemical_system_id__in: list[ShortStr] | None = None
    chemical_system_id__neq: ShortStr | None = None
    chemical_system_id__ilike: str | None = None

    formula: str | None = None
    formula__in: list[ShortStr] | None = None
    formula__neq: ShortStr | None = None
    formula__ilike: str | None = None

    unique_value: Scalar | None = None
    unique_value__in: list[Scalar] | None = None
    unique_value__neq: Scalar | None = None

    condition_key: str | None = None
    condition_key__in: list[str] | None = None
    condition_key__neq: str | None = None
    condition_key__ilike: str | None = None

    is_public: bool | None = None

    table: TableFilter | None = FilterDepends(with_prefix("tables", TableFilter))
    attachment: AttachmentFilter | None = FilterDepends(with_prefix("attachments", AttachmentFilter))
    structure: StructureFilter | None = FilterDepends(with_prefix("structures", StructureFilter))

    # sorting
    order_by: list[str] | None = None

    class Constants(BaseFilter.Constants):
        model = Contribution

    @field_validator("id", mode="before")
    @classmethod
    def convert_str_to_oid(cls, v: str):
        try:
            return PydanticObjectId(v)
        except InvalidId as err:
            raise ValidationError(
                "Invalid ObjectId format. Must be 12-byte input or a 24-character hex string",
                oid=v,
            ) from err
