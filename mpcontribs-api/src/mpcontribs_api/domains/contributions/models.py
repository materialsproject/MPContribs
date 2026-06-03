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
from fastapi_filter.contrib.beanie import Filter
from pydantic import Field

from src.mpcontribs_api.domains._shared.models import BaseDocumentWithInput, DocumentOut
from src.mpcontribs_api.domains.attachments.models import Attachment
from src.mpcontribs_api.domains.structures.models import Structure
from src.mpcontribs_api.domains.tables.models import Table
from src.mpcontribs_api.projection import SparseFieldsModel
from src.mpcontribs_api.types import ShortStr


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

    # sorting
    order_by: list[str] | None = None

    class Constants(Filter.Constants):
        model = Contribution
