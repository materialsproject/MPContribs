from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from mpcontribs_api import pagination
from mpcontribs_api.domains._shared.filters import BaseFilter
from mpcontribs_api.domains._shared.models import BaseDocumentWithInput, DocumentOut
from mpcontribs_api.domains._shared.types import PrefixedEmail, ShortStr


class Column(BaseModel):
    path: str
    min: float | None = None
    max: float | None = None
    unit: str | None = None

    @property
    def segments(self) -> tuple[str, ...]:
        return tuple(self.path.split("."))


class Stats(BaseModel):
    columns: int
    contributions: int
    tables: int
    structures: int
    attachments: int
    size: float


class Reference(BaseModel):
    # TODO: Labels have some restrictions, not sure exactly what yet
    label: str
    url: HttpUrl


class Project(BaseDocumentWithInput[ShortStr]):
    """Document model of what is actually stored.

    Binds ``id`` to ``ShortStr`` (a meaningful string id, always supplied) via the generic base.
    """

    # Required
    title: ShortStr
    authors: str
    description: str
    owner: PrefixedEmail
    unique_identifiers: bool
    stats: Stats

    # Optional
    category: ShortStr | None = None
    references: list[Reference] = Field(default_factory=list)
    long_title: str | None = None
    other: dict[str, Any] = Field(default_factory=dict)
    columns: list[Column] = Field(default_factory=list)
    is_public: bool = False
    is_approved: bool = False
    license: Literal["CCA4", "CCPD"] | None = None

    # Empty method for now. Keeping for business logic later
    @classmethod
    def from_input_model(cls, data: ProjectIn) -> Project:
        return cls(**data.model_dump())

    @staticmethod
    def decode_cursor(cursor: str) -> str:
        """Decodes cursor and returns it as a str.

        Needs override over parent class since Project.id is a simple str
        """
        return pagination.decode_cursor(cursor)

    class Settings:
        name = "projects"
        keep_nulls = False


class ProjectOut(DocumentOut[ShortStr]):
    """Full response of all public-facing fields."""

    model_config = ConfigDict(extra="ignore")
    authors: str | None = None
    description: str | None = None
    title: ShortStr | None = None
    category: ShortStr | None = None
    owner: PrefixedEmail | None = None
    other: dict[str, Any] | None = None
    is_public: bool | None = None
    is_approved: bool | None = None
    long_title: str | None = None
    unique_identifiers: bool | None = None
    references: list[Reference] | None = None
    stats: Stats | None = None
    columns: list[Column] | None = None
    license: Literal["CCA4", "CCPD"] | None = None

    @staticmethod
    def default_fields() -> list[str]:
        return ["id", "is_public", "title", "owner", "is_approved", "unique_identifiers"]


class ProjectFilter(BaseFilter):
    """Filter fields allowed in requests."""

    id: ShortStr | None = None
    id__in: list[ShortStr] | None = None
    id__neq: ShortStr | None = None

    title: ShortStr | None = None
    title__in: list[ShortStr] | None = None
    title__neq: ShortStr | None = None
    title__ilike: str | None = None

    owner: PrefixedEmail | None = None
    owner__in: list[PrefixedEmail] | None = None
    owner__neq: PrefixedEmail | None = None
    owner__ilike: str | None = None

    category: ShortStr | None = None
    category__in: list[ShortStr] | None = None
    category__neq: ShortStr | None = None
    category__ilike: str | None = None

    # fuzzy only
    long_title__ilike: str | None = None

    is_public: bool | None = None
    is_approved: bool | None = None
    unique_identifiers: bool | None = None

    license: Literal["CCA4", "CCPD"] | None = None
    license__in: list[Literal["CCA4", "CCPD"]] | None = None

    # sorting
    order_by: list[str] | None = None

    class Constants(BaseFilter.Constants):
        model = Project


# Keeping for business logic separation. May have specific implementation later
class ProjectIn(Project):
    """Representation of user-supplied input."""

    pass


class ProjectPatch(BaseModel):
    """Nullable Project representation of user-supplied data for partial update (patch)."""

    title: ShortStr | None = None
    authors: str | None = None
    description: str | None = None
    category: ShortStr | None = None
    owner: PrefixedEmail | None = None
    unique_identifiers: bool | None = None
    references: list[Reference] = Field(default_factory=list)
    long_title: str | None = None
    other: dict[str, Any] = Field(default_factory=dict)
    columns: list[Column] = Field(default_factory=list)
    is_public: bool | None = None
    is_approved: bool | None = None
    license: Literal["CCA4", "CCPD"] | None = None
