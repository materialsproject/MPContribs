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
from fastapi_filter import FilterDepends, with_prefix
from fastapi_filter.contrib.beanie import Filter
from pydantic import Field

from mpcontribs_api.domains._shared.models import BaseDocumentWithInput, DocumentOut
from mpcontribs_api.domains.attachments.models import Attachment, AttachmentFilter
from mpcontribs_api.domains.structures.models import Structure, StructureFilter
from mpcontribs_api.domains.tables.models import Table, TableFilter
from mpcontribs_api.projection import SparseFieldsModel
from mpcontribs_api.types import ShortStr


class ContributionBase(BaseDocumentWithInput[PydanticObjectId]):
    project: str
    identifier: str
    formula: str
    data: dict[str, Any]

    # TODO: Verify that this should default to True and be passed by users
    needs_build: bool = True
    last_modified: datetime = Field(default_factory=lambda: datetime.now(UTC))
    structures: list[Link[Structure]] | None = None
    tables: list[Link[Table]] | None = None
    attachments: list[Link[Attachment]] | None = None

    class Settings:
        name = "contributions"
        keep_nulls = False


class Contribution(ContributionBase):
    is_public: bool
    # needs_build: bool = True

    @classmethod
    def from_input_model(cls, data: ContributionIn) -> Contribution:
        return cls.model_validate(
            {
                **data.model_dump(exclude={"is_public"}),
                "is_public": False,
            }
        )

    @before_event(Insert, Replace, Update, Save, SaveChanges)
    def set_last_modified(self):
        self.last_modified = datetime.now(UTC)


class ContributionIn(ContributionBase):
    pass


class ContributionOut(DocumentOut[PydanticObjectId]):
    project: str | None = None
    identifier: str | None = None
    formula: str | None = None
    is_public: bool | None = None
    last_modified: datetime | None = None
    needs_build: bool | None = None
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
    data: dict[str, Any] | None = None
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
