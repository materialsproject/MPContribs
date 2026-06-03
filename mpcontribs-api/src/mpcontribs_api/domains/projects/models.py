from __future__ import annotations

from typing import Annotated, Any, Literal

from beanie import DocumentWithSoftDelete
from fastapi_filter.contrib.beanie import Filter
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from src.mpcontribs_api.projection import SparseFieldsModel
from src.mpcontribs_api.types import PrefixedEmail, ShortStr


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


class Project(DocumentWithSoftDelete):
    """Document model of what is actually stored."""

    # Required
    # meaningful string id, always supplied
    id: ShortStr = Field(alias="_id")  # pyright: ignore[reportGeneralTypeIssues, reportIncompatibleVariableOverride]
    title: ShortStr
    authors: str
    description: str
    owner: PrefixedEmail
    unique_identifiers: bool
    stats: Stats

    # Optional
    references: list[Reference] = Field(default_factory=list)
    long_title: str | None = None
    other: dict[str, Any] = Field(default_factory=dict)
    columns: list[Column] = Field(default_factory=list)
    is_public: bool = False
    is_approved: bool = False
    license: Literal["CCA4", "CCPD"] | None = None

    # Empty method for now. Keeping for business logic later
    @classmethod
    def from_project_in(cls, data: ProjectIn) -> Project:
        return cls(**data.model_dump())

    class Settings:
        name = "projects"
        keep_nulls = False


class ProjectOut(SparseFieldsModel):
    """Full response of all public-facing fields."""

    model_config = ConfigDict(extra="ignore")
    id: Annotated[ShortStr | None, Field(alias="_id", serialization_alias="id")] = None
    authors: str | None = None
    description: str | None = None
    title: ShortStr | None = None
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


class ProjectFilter(Filter):
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

    # fuzzy only
    long_title__ilike: str | None = None

    is_public: bool | None = None
    is_approved: bool | None = None
    unique_identifiers: bool | None = None

    license: Literal["CCA4", "CCPD"] | None = None
    license__in: list[Literal["CCA4", "CCPD"]] | None = None

    # sorting
    order_by: list[str] | None = None

    class Constants(Filter.Constants):
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
    owner: PrefixedEmail | None = None
    unique_identifiers: bool | None = None
    references: list[Reference] = Field(default_factory=list)
    long_title: str | None = None
    other: dict[str, Any] = Field(default_factory=dict)
    columns: list[Column] = Field(default_factory=list)
    is_public: bool = False
    is_approved: bool = False
    license: Literal["CCA4", "CCPD"] | None = None
