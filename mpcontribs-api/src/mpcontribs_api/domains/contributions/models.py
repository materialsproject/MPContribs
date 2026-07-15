import re
from datetime import UTC, datetime
from typing import Annotated, Any
from warnings import deprecated

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
from pydantic import BeforeValidator, Field, field_validator
from pymongo import ASCENDING, IndexModel

from mpcontribs_api.domains._shared.filters import BaseFilter
from mpcontribs_api.domains._shared.models import BaseDocumentWithInput, DocumentOut
from mpcontribs_api.domains._shared.types import ShortStr
from mpcontribs_api.domains.attachments.models import Attachment, AttachmentFilter, AttachmentIn
from mpcontribs_api.domains.structures.models import Structure, StructureFilter, StructureIn
from mpcontribs_api.domains.tables.models import Table, TableFilter, TableIn
from mpcontribs_api.exceptions import ValidationError
from mpcontribs_api.projection import SparseFieldsModel


def _get_dict_depth(x) -> int:
    if isinstance(x, dict):
        return 1 + max((_get_dict_depth(v) for v in x.values()), default=0)
    elif isinstance(x, list):
        return max((_get_dict_depth(item) for item in x), default=0)
    return 0


def _validate_data_depth(data: dict[str, Any] | None) -> dict[str, Any] | None:
    if data is None:
        return None
    depth = _get_dict_depth(data)
    if depth > 7:
        raise ValidationError("Depth of Contribution.data must be <= 7.", depth=depth)
    return data


# Forbid punctuation, excluding: '*', '/' and exactly 1 '|' anywhere in string
_DATA_PUNCTUATION_PATTERN = re.compile(r"(?![^|]*\|[^|]*\|)[^\x21-\x29\x2B-\x2E\x3A-\x40\x5B-\x5E\x60\x7B\x7D-\x7E]*")


def _validate_keys(data: dict[str, Any] | None) -> dict[str, Any] | None:
    if data is None:
        return None
    keys = list(data.keys())
    if not all(isinstance(k, str) and k.isascii() for k in keys):
        raise ValidationError("Non-ASCII key found in Contribution.data. All dict keys must be only ASCII")
    if any(k == "" for k in keys):
        raise ValidationError("Empty key found in Contribution.data. Keys must be non-empty.")
    if any(_DATA_PUNCTUATION_PATTERN.fullmatch(k) is None for k in keys):
        raise ValidationError(
            "Punctuation found in Contribution.data keys. Only '_', '*', '/', and at most 1 '|' permitted."
        )
    # Recurse into nested dicts, including dicts nested inside lists.
    for v in data.values():
        _validate_nested_keys(v)
    return data


def _validate_nested_keys(value: Any) -> None:
    if isinstance(value, dict):
        _validate_keys(value)
    elif isinstance(value, list):
        for item in value:
            _validate_nested_keys(item)


class ContributionBase(BaseDocumentWithInput[PydanticObjectId]):
    """Shared settings and fields for Contribution, ContributionIn, and ContributionOut."""

    project: str
    identifier: str
    formula: str
    is_public: bool = False
    data: Annotated[
        dict[str, Any],
        BeforeValidator(_validate_data_depth),
        BeforeValidator(_validate_keys),
    ]

    last_modified: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "contributions"
        keep_nulls = False
        indexes = [
            IndexModel(
                keys=[("project", ASCENDING), ("identifier", ASCENDING), ("version", ASCENDING)],
                name="project_identifier_version",
                unique=True,
            ),
            # Multikey indexes over each Link field's DBRef id so the component-delete
            # reference check (referenced_component_ids) is index-served, not a COLLSCAN.
            IndexModel(keys=[("structures.$id", ASCENDING)], name="ref_structures"),
            IndexModel(keys=[("tables.$id", ASCENDING)], name="ref_tables"),
            IndexModel(keys=[("attachments.$id", ASCENDING)], name="ref_attachments"),
        ]

    @classmethod
    def identifier_fields(cls) -> frozenset[str]:
        """A contribution is uniquely identified (within a version) by ``project`` + ``identifier``."""
        return frozenset({"project", "identifier"})


class Contribution(ContributionBase):
    """Models what is actually stored in the database."""

    # Server-owned: the service resolves the real version (see ContributionService._split_non_unique)
    # and stamps it on the doc. Defaults to 1 so the no-version (unique-identifier) case is implicit.
    version: int = 1
    structures: list[Link[Structure]] | None = None
    tables: list[Link[Table]] | None = None
    attachments: list[Link[Attachment]] | None = None
    needs_build: Annotated[bool | None, deprecated("'needs_build' is deprecated.")] = False

    @classmethod
    def from_input_model(cls, data: ContributionIn) -> Contribution:
        # Server-owned fields are not taken from input: is_public starts False, components are
        # inserted separately, last_modified is stamped by the before_event hook, and version is
        # resolved/stamped by the service (never trusted from the request body).
        return cls.model_validate(
            {
                **data.model_dump(
                    exclude={"is_public", "version", "structures", "tables", "attachments", "last_modified"}
                ),
                "is_public": False,
            }
        )

    @before_event(Insert, Replace, Update, Save, SaveChanges)
    def set_last_modified(self):
        self.last_modified = datetime.now(UTC)


class ContributionIn(ContributionBase):
    """Fields that users are allowed to submit when adding a Contribution.

    version will be inferred if left as None
    """

    # Only meaningful on upsert/update of a non-unique-identifier project, where it selects which
    # version to target. Ignored on insert (the service auto-assigns) and for unique-identifier
    # projects (inferred as 1).
    version: int | None = None
    structures: list[StructureIn] | None = None
    tables: list[TableIn] | None = None
    attachments: list[AttachmentIn] | None = None

    def has_components(self) -> bool:
        """Returns ``True`` if the contribution has any components (structures, tables, attachments)"""
        return bool(self.structures or self.tables or self.attachments)

    def component_count(self) -> int:
        """Returns the total number of components (structures, tables, attachments) in the contribution"""
        return len(self.structures or []) + len(self.tables or []) + len(self.attachments or [])

    def identifiers(self) -> dict[str, str]:
        """Returns this contribution's identifier values (see ``identifier_fields``).

        Overrides the base to narrow the value type to ``str`` for the callers (bulk error
        reporting, ``upsert_contribution_by_identifiers``) that key on it.
        """
        return {"project": self.project, "identifier": self.identifier}


class ContributionOut(DocumentOut[PydanticObjectId]):
    """Models what the users are allowed to see in a return.

    Users can specify further what they want to see if not everything is of interest
    """

    project: str | None = None
    identifier: str | None = None
    version: int | None = None
    formula: str | None = None
    is_public: bool | None = None
    last_modified: datetime | None = None
    needs_build: Annotated[bool | None, deprecated("'needs_build' is deprecated.")] = None
    # No input validators on the read path: stored documents are trusted, and re-validating here
    # would 500 on historical data that missed the correction (see carrier_transport contribs)
    data: dict[str, Any] | None = None
    structures: list[Link[Structure]] | None = None
    tables: list[Link[Table]] | None = None
    attachments: list[Link[Attachment]] | None = None

    @staticmethod
    def default_fields() -> list[str]:
        return [
            "id",
            "project",
            "identifier",
            "version",
            "formula",
            "is_public",
            "last_modified",
        ]


class ContributionPatch(SparseFieldsModel):
    """Fields that can be specified for partial updates to a Contribution."""

    project: str | None = None
    identifier: str | None = None
    version: int | None = None
    formula: str | None = None
    is_public: bool | None = None
    data: Annotated[
        dict[str, Any] | None,
        BeforeValidator(_validate_data_depth),
        BeforeValidator(_validate_keys),
    ] = None
    structures: list[Link[Structure]] | None = None
    tables: list[Link[Table]] | None = None
    attachments: list[Link[Attachment]] | None = None


class ContributionFilter(BaseFilter):
    """How users can filter searches for Contributions.

    Includes filters for linked documents (Components)
    """

    id: PydanticObjectId | None = None
    id__in: list[PydanticObjectId] | None = None
    id__neq: PydanticObjectId | None = None

    identifier: str | None = None
    identifier__in: list[ShortStr] | None = None
    identifier__neq: ShortStr | None = None
    identifier__ilike: str | None = None

    version: str | None = None
    version__in: list[ShortStr] | None = None
    version__neq: ShortStr | None = None
    version__ilike: str | None = None

    formula: str | None = None
    formula__in: list[ShortStr] | None = None
    formula__neq: ShortStr | None = None
    formula__ilike: str | None = None

    is_public: bool | None = None

    needs_build: bool | None = None

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
