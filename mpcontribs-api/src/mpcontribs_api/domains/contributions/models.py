from datetime import UTC, datetime
from enum import StrEnum
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
from pydantic import Field, field_validator, model_validator
from pymongo import ASCENDING, IndexModel

from mpcontribs_api._openapi import CONTRIBUTION_DATA_OUTPUT_DESCRIPTION
from mpcontribs_api.domains._shared.filters import BaseFilter
from mpcontribs_api.domains._shared.models import BaseDocumentWithInput, DocumentOut
from mpcontribs_api.domains._shared.search_index import SearchIndex, SearchIndexed
from mpcontribs_api.domains._shared.types import ChemicalSystemId, Formula, Identity, MaterialId, Scalar, ShortStr
from mpcontribs_api.domains.attachments.models import Attachment, AttachmentFilter
from mpcontribs_api.domains.contributions.data import ContributionStoredData
from mpcontribs_api.domains.structures.models import Structure, StructureFilter
from mpcontribs_api.domains.tables.models import Table, TableFilter
from mpcontribs_api.exceptions import ValidationError


class ContributionIdentity(Identity):
    """The full identity of a Contribution.

    Field declaration order IS the identity/index column order: ``index_model`` and ``projection``
    iterate ``model_fields`` in that order, so the order is declared exactly once (below).
    """

    # WARNING: the order the fields are specified in reflects their ordering for indices. Changing the order
    # creates index migration. Only change intentionally
    project: str
    material_id: MaterialId | None = None
    chemical_system_id: ChemicalSystemId
    formula: Formula | None = None
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

    @model_validator(mode="after")
    def _check_identifier_hierarchy(self) -> ContributionIdentity:
        """Enforce ``chemical_system_id`` > ``formula`` > ``material_id`` whenever an identity is built.

        Bound directly as the ``/item`` query params, so every selector verb (read, patch, delete)
        rejects a bad hierarchy with a 422 at the query boundary rather than relying on a downstream
        ``read_one`` resolution to catch it. ``from_document`` uses ``model_construct`` and skips
        validators, so trusted stored documents are unaffected.
        """
        ContributionIdentity.check_hierarchy(self.material_id, self.chemical_system_id, self.formula)
        return self


class ContributionSearchIndex(StrEnum):
    """Names of Contribution's Atlas Search indexes."""

    FORMULA_AUTOCOMPLETE = "formula_autocomplete"


class Contribution(
    BaseDocumentWithInput[PydanticObjectId],
    SearchIndexed,
):
    """Models what is actually stored in the database."""

    identity_model: ClassVar[type[Identity]] = ContributionIdentity

    # Identifiers follow a specificity hierarchy: chemical_system_id > formula > material_id.
    # chemical_system_id is always required.
    project: str
    material_id: str | None = None
    chemical_system_id: str
    formula: str | None = None
    is_public: bool = False
    # Strict validation over stored data rather than coercion.
    data: ContributionStoredData
    last_modified: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Server owner - uses Project.unique_column to extract the value from Contribution.data
    unique_value: Scalar | None = None
    # Server-owned pivot-condition discriminator; "" until pivoting is wired in (see Identity).
    condition_key: str = ""
    structures: list[Link[Structure]] | None = None
    tables: list[Link[Table]] | None = None
    attachments: list[Link[Attachment]] | None = None

    class Settings:
        name = "contributions"
        keep_nulls = False
        indexes = [
            ContributionIdentity.index_model(name="project_identity"),
            # Multikey indexes over each Link field's DBRef id so the component-delete
            # reference check is index-served, not a COLLSCAN.
            IndexModel(keys=[("structures.$id", ASCENDING)], name="ref_structures"),
            IndexModel(keys=[("tables.$id", ASCENDING)], name="ref_tables"),
            IndexModel(keys=[("attachments.$id", ASCENDING)], name="ref_attachments"),
        ]

    @classmethod
    def search_indexes(cls) -> tuple[SearchIndex, ...]:
        return (
            SearchIndex(
                # TODO: formula autocomplete doesn't use `type: autocomplete` for formula
                name=ContributionSearchIndex.FORMULA_AUTOCOMPLETE,
                type="search",
                definition={
                    "analyzer": "lucene.whitespace",
                    "searchAnalyzer": "lucene.whitespace",
                    "mappings": {
                        "dynamic": False,
                        "fields": {
                            # TODO: Why do we index data for a formula autocomplete?
                            cls._path("data"): {"dynamic": True, "type": "document"},
                            cls._path("formula"): {"type": "string"},
                            cls._path("material_id"): {"type": "string"},
                            cls._path("chemical_system_id"): {"type": "string"},
                            cls._path("unique_value"): {"type": "string"},
                            cls._path("condition_key"): {"type": "string"},
                            cls._path("is_public"): {"type": "boolean"},
                            cls._path("last_modified"): {"type": "date"},
                            cls._path("project"): [{"type": "stringFacet"}, {"type": "string"}],
                        },
                    },
                    # TODO: remove data from storedSource
                    "storedSource": True,
                },
            ),
        )

    @before_event(Insert, Replace, Update, Save, SaveChanges)
    def set_last_modified(self):
        self.last_modified = datetime.now(UTC)


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
