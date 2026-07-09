import re
from datetime import UTC, datetime
from typing import Annotated, Any

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
from mpcontribs_api.domains.contributions.pivot import parse_annotated_key
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


def _validate_plain_key(key: Any) -> None:
    """Validate a single plain key token (a path segment or a condition name)."""
    if not isinstance(key, str) or not key.isascii():
        raise ValidationError("Non-ASCII key found in Contribution.data. All dict keys must be only ASCII")
    if key == "":
        raise ValidationError("Empty key found in Contribution.data. Keys must be non-empty.")
    if _DATA_PUNCTUATION_PATTERN.fullmatch(key) is None:
        raise ValidationError(
            "Punctuation found in Contribution.data keys. Only '_', '*', '/', and at most 1 '|' permitted."
        )


def _validate_keys(data: dict[str, Any] | None) -> dict[str, Any] | None:
    """Strict plain-key validation for a single dict level (used for nested levels)."""
    if data is None:
        return None
    for key in data:
        _validate_plain_key(key)
    # Recurse into nested dicts, including dicts nested inside lists.
    for v in data.values():
        _validate_nested_keys(v)
    return data


def _validate_data_keys(data: dict[str, Any] | None) -> dict[str, Any] | None:
    """Top-level ``data`` key validation, allowing the annotated pattern.

    Each top-level key may be either a plain key or the annotated form
    ``name (unit, cond1=..., cond2=...)``. The name's dotted segments and every condition name are
    held to the same plain-key rules (units are unconstrained); nested levels stay strictly plain.
    Expansion (see :mod:`mpcontribs_api.domains.contributions.pivot`) later rewrites annotated keys
    into plain ones, so stored keys always satisfy :func:`_validate_keys`.
    """
    if data is None:
        return None
    for raw_key in data:
        if not isinstance(raw_key, str):
            raise ValidationError("Non-ASCII key found in Contribution.data. All dict keys must be only ASCII")
        try:
            parsed = parse_annotated_key(raw_key)
        except ValueError as err:
            raise ValidationError(f"Malformed annotated key in Contribution.data: {err}") from err
        if not parsed.is_annotated:
            # A plain key keeps the original strict rule (no '.' nesting); only annotated keys may
            # use dotted paths, whose segments are validated individually below.
            _validate_plain_key(raw_key)
            continue
        for segment in parsed.segments:
            _validate_plain_key(segment)
        for condition_name in parsed.conditions:
            _validate_plain_key(condition_name)
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
    project: str
    identifier: str
    formula: str
    data: Annotated[
        dict[str, Any],
        BeforeValidator(_validate_data_depth),
        BeforeValidator(_validate_data_keys),
    ]

    # TODO: Verify that this should default to True and be passed by users
    needs_build: bool = True
    last_modified: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "contributions"
        keep_nulls = False
        indexes = [
            # condition_key is part of identity so pivoted rows (same project/identifier, different
            # conditions) coexist; legacy docs use the "" default. See ContributionService and
            # mpcontribs_api.domains.contributions.pivot.
            IndexModel(
                keys=[
                    ("project", ASCENDING),
                    ("identifier", ASCENDING),
                    ("condition_key", ASCENDING),
                    ("version", ASCENDING),
                ],
                name="project_identifier_conditionkey_version",
                unique=True,
            ),
            # Multikey indexes over each Link field's DBRef id so the component-delete
            # reference check (referenced_component_ids) is index-served, not a COLLSCAN.
            IndexModel(keys=[("structures.$id", ASCENDING)], name="ref_structures"),
            IndexModel(keys=[("tables.$id", ASCENDING)], name="ref_tables"),
            IndexModel(keys=[("attachments.$id", ASCENDING)], name="ref_attachments"),
        ]


class Contribution(ContributionBase):
    is_public: bool
    # Server-owned: the service resolves the real version (see ContributionService._split_non_unique)
    # and stamps it on the doc. Defaults to 1 so the no-version (unique-identifier) case is implicit.
    version: int = 1
    # Server-owned: a deterministic canonical string of the pivot conditions (see
    # mpcontribs_api.domains.contributions.pivot). "" means no conditions (every legacy doc). Part of
    # the unique index so pivoted rows can share (project, identifier).
    condition_key: str = ""
    structures: list[Link[Structure]] | None = None
    tables: list[Link[Table]] | None = None
    attachments: list[Link[Attachment]] | None = None
    # needs_build: bool = True

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
    # Only meaningful on upsert/update of a non-unique-identifier project, where it selects which
    # version to target. Ignored on insert (the service auto-assigns) and for unique-identifier
    # projects (inferred as 1). Kept optional (``None`` == "not supplied") so the service can tell an
    # omitted version from an explicit ``1`` and require one only in the ambiguous upsert case (see
    # ContributionService._split_non_unique); it resolves ``None`` -> 1 when unambiguous.
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

    def identifiers(self) -> dict[str, str | int | None]:
        """Returns a dict of unique identifiers for a contribution (outside of id).

        ``version`` is the raw request value (``None`` when omitted); the service overrides it with
        the resolved version before using it to target a row (see ContributionService).
        """
        return {
            "project": self.project,
            "identifier": self.identifier,
            "version": self.version,
        }


class ContributionOut(DocumentOut[PydanticObjectId]):
    project: str | None = None
    identifier: str | None = None
    version: int | None = None
    condition_key: str | None = None
    formula: str | None = None
    is_public: bool | None = None
    last_modified: datetime | None = None
    needs_build: bool | None = None
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
            "condition_key",
            "formula",
            "is_public",
            "last_modified",
            "needs_build",
        ]


class ContributionPatch(SparseFieldsModel):
    project: str | None = None
    identifier: str | None = None
    version: int | None = None
    formula: str | None = None
    needs_build: bool | None = None
    data: Annotated[
        dict[str, Any] | None,
        BeforeValidator(_validate_data_depth),
        BeforeValidator(_validate_keys),
    ] = None
    structures: list[Link[Structure]] | None = None
    tables: list[Link[Table]] | None = None
    attachments: list[Link[Attachment]] | None = None


class ContributionFilter(BaseFilter):
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
