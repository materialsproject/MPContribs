from datetime import UTC, datetime
from typing import Any

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
from pydantic import Field, field_validator
from pymongo import ASCENDING, IndexModel

from mpcontribs_api._openapi import CONTRIBUTION_DATA_INPUT_DESCRIPTION, CONTRIBUTION_DATA_OUTPUT_DESCRIPTION
from mpcontribs_api.domains._shared.filters import BaseFilter
from mpcontribs_api.domains._shared.models import BaseDocumentWithInput, DocumentOut
from mpcontribs_api.domains._shared.types import ContributionData, DisplayStr, SearchStr, ShortStr
from mpcontribs_api.domains.attachments.models import Attachment, AttachmentFilter, AttachmentIn
from mpcontribs_api.domains.structures.models import Structure, StructureFilter, StructureIn
from mpcontribs_api.domains.tables.models import Table, TableFilter, TableIn
from mpcontribs_api.exceptions import ValidationError
from mpcontribs_api.projection import SparseFieldsModel


class ContributionBase(BaseDocumentWithInput[PydanticObjectId]):
    project: ShortStr
    identifier: SearchStr
    formula: DisplayStr
    data: ContributionData = Field(description=CONTRIBUTION_DATA_INPUT_DESCRIPTION)

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
    data: dict[str, Any] | None = Field(default=None, description=CONTRIBUTION_DATA_OUTPUT_DESCRIPTION)
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
    project: ShortStr | None = None
    identifier: SearchStr | None = None
    version: int | None = None
    formula: DisplayStr | None = None
    needs_build: bool | None = None
    data: ContributionData = Field(default=None, description=CONTRIBUTION_DATA_INPUT_DESCRIPTION)
    structures: list[Link[Structure]] | None = None
    tables: list[Link[Table]] | None = None
    attachments: list[Link[Attachment]] | None = None


class ContributionFilter(BaseFilter):
    id: PydanticObjectId | None = None
    id__in: list[PydanticObjectId] | None = None
    id__neq: PydanticObjectId | None = None

    identifier: SearchStr | None = None
    identifier__in: list[SearchStr] | None = None
    identifier__neq: SearchStr | None = None
    identifier__ilike: SearchStr | None = None

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
