from enum import Enum
from typing import Annotated, Any, Literal

from beanie import DocumentWithSoftDelete
from fastapi_filter.contrib.beanie import Filter
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

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

    # meaningful string id, always supplied
    id: ShortStr = Field(alias="_id")  # pyright: ignore[reportGeneralTypeIssues, reportIncompatibleVariableOverride]
    title: ShortStr
    authors: str
    description: str
    owner: PrefixedEmail
    other: dict[str, Any]
    is_public: bool = False
    is_approved: bool = False
    long_title: str
    unique_identifiers: bool
    references: list[Reference]
    stats: Stats
    columns: list[Column]
    license: Literal["CCA4", "CCPD"] | None = None


# Project Responses
class ProjectSummary(BaseModel):
    """Subset of fields to return when not all info is desired."""

    id: Annotated[ShortStr, Field(alias="_id")]
    owner: PrefixedEmail
    unique_identifiers: bool
    is_public: bool = False
    is_approved: bool = False
    title: ShortStr


class ProjectResponse(BaseModel):
    """Full response of all public-facing fields."""

    model_config = ConfigDict(extra="ignore")
    id: Annotated[ShortStr | None, Field(alias="_id")] = None
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


# Filter to use for Projects
class ProjectFilter(Filter):
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


# Enum to determine which response model to use
class ProjectView(str, Enum):
    full = "full"
    summary = "summary"


_VIEW_MODELS: dict[ProjectView, type[BaseModel]] = {
    ProjectView.full: ProjectResponse,
    ProjectView.summary: ProjectSummary,
}
