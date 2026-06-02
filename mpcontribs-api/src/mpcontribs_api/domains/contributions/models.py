from datetime import datetime
from typing import Any

from beanie import Document, Link
from fastapi_filter.contrib.beanie import Filter

from src.mpcontribs_api.domains.attachments.models import Attachment
from src.mpcontribs_api.domains.structures.models import Structure
from src.mpcontribs_api.domains.tables.models import Table
from src.mpcontribs_api.projection import SparseFieldsModel
from src.mpcontribs_api.types import ShortStr


class Contribution(Document):
    project: str
    identifier: str
    formula: str
    is_public: bool = False
    last_modified: datetime
    needs_build: bool = True
    data: dict[str, Any]
    structures: list[Link[Structure]] | None = None
    tables: list[Link[Table]] | None = None
    attachments: list[Link[Attachment]] | None = None


class ContributionOut(SparseFieldsModel):
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


class ContributionFilter(Filter):
    id: str | None = None
    id__in: list[str] | None = None
    id__neq: str | None = None

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
