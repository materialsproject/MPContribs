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
from fastapi_filter import FilterDepends, with_prefix
from fastapi_filter.contrib.beanie import Filter
from pydantic import BeforeValidator, Field, field_validator
from pymongo import ASCENDING, IndexModel

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
    if not data:
        return None
    depth = _get_dict_depth(data)
    if depth > 7:
        raise ValidationError("Depth of Contribution.data must be <= 7.", depth=depth)
    return data


class ContributionBase(BaseDocumentWithInput[PydanticObjectId]):
    project: str
    identifier: str
    formula: str
    data: Annotated[dict[str, Any], BeforeValidator(_validate_data_depth)]

    # TODO: Verify that this should default to True and be passed by users
    needs_build: bool = True
    last_modified: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "contributions"
        keep_nulls = False
        indexes = [
            IndexModel(
                keys=[("project", ASCENDING), ("identifier", ASCENDING)],
                name="project_idenfitier",
                unique=True,
            )
        ]


class Contribution(ContributionBase):
    is_public: bool
    structures: list[Link[Structure]] | None = None
    tables: list[Link[Table]] | None = None
    attachments: list[Link[Attachment]] | None = None
    # needs_build: bool = True

    @classmethod
    def from_input_model(cls, data: ContributionIn) -> Contribution:
        return cls.model_validate(
            {
                **data.model_dump(exclude={"is_public", "structures", "tables", "attachments"}),
                "is_public": False,
            }
        )

    @before_event(Insert, Replace, Update, Save, SaveChanges)
    def set_last_modified(self):
        self.last_modified = datetime.now(UTC)


class ContributionIn(ContributionBase):
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
        """Returns a dict of unique identifiers for a contribution (outside of id)."""
        return {"project": self.project, "identifier": self.identifier}


class ContributionOut(DocumentOut[PydanticObjectId]):
    project: str | None = None
    identifier: str | None = None
    formula: str | None = None
    is_public: bool | None = None
    last_modified: datetime | None = None
    needs_build: bool | None = None
    data: Annotated[dict[str, Any] | None, BeforeValidator(_validate_data_depth)] = None
    structures: list[Link[Structure]] | None = None
    tables: list[Link[Table]] | None = None
    attachments: list[Link[Attachment]] | None = None

    @staticmethod
    def default_fields() -> list[str]:
        return [
            "id",
            "project",
            "identifier",
            "formula",
            "is_public",
            "last_modified",
            "needs_build",
        ]


class ContributionPatch(SparseFieldsModel):
    project: str | None = None
    identifier: str | None = None
    formula: str | None = None
    needs_build: bool | None = None
    data: Annotated[dict[str, Any] | None, BeforeValidator(_validate_data_depth)] = None
    structures: list[Link[Structure]] | None = None
    tables: list[Link[Table]] | None = None
    attachments: list[Link[Attachment]] | None = None


class ContributionFilter(Filter):
    id: PydanticObjectId | None = None
    id__in: list[PydanticObjectId] | None = None
    id__neq: PydanticObjectId | None = None

    identifier: str | None = None
    identifier__in: list[ShortStr] | None = None
    identifier__neq: ShortStr | None = None
    identifier__ilike: str | None = None

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

    class Constants(Filter.Constants):
        model = Contribution

    @field_validator("id", mode="before")
    @classmethod
    def convert_str_to_oid(cls, v: str):
        return PydanticObjectId(v)
