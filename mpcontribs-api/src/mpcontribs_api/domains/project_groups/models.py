from beanie import Link, PydanticObjectId
from bson import DBRef
from bson.errors import InvalidId
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pymongo import ASCENDING, IndexModel

from mpcontribs_api.domains._shared.filters import BaseFilter
from mpcontribs_api.domains._shared.models import BaseDocumentWithInput, DocumentOut
from mpcontribs_api.domains._shared.types import PrefixedEmail, SearchStr, ShortStr
from mpcontribs_api.domains.projects.models import Project
from mpcontribs_api.exceptions import ValidationError
from mpcontribs_api.projection import SparseFieldsModel


class ProjectGroup(BaseDocumentWithInput[PydanticObjectId]):
    name: SearchStr = Field(max_length=50)
    owner: PrefixedEmail
    description: str = Field(max_length=100)
    is_public: bool = False
    projects: list[Link[Project]] | None = None

    class Settings:
        name = "project_groups"
        indexes = [
            IndexModel(
                keys=[("name", ASCENDING), ("owner", ASCENDING)],
                name="name_owner",
                unique=True,
            ),
            IndexModel(
                keys=[("name", ASCENDING), ("owner", ASCENDING), ("is_public", ASCENDING)],
                name="name_owner_is_public",
            ),
        ]
        validate_on_save = True

    @classmethod
    def identifier_fields(cls) -> frozenset[str]:
        """A ``ProjectGroup`` is uniquely identified by its ``name`` + ``owner``."""
        return frozenset({"name", "owner"})

    @classmethod
    def from_input_model(cls, data: ProjectGroupIn) -> ProjectGroup:
        """Build a stored group from input, assigning a fresh ``_id`` and resolving member ids to links"""
        payload = data.model_dump()
        project_ids = payload.pop("projects", None) or []
        payload["_id"] = PydanticObjectId()
        payload["projects"] = [DBRef("projects", pid) for pid in project_ids]
        return cls.model_validate(payload)

    @field_validator("projects")
    @classmethod
    def _reject_duplicate_refs(
        cls,
        value: list[Link[Project] | Project] | None,
    ) -> list[Link[Project] | Project] | None:
        if value is None:
            return value
        seen: set[ShortStr] = set()
        for item in value:
            ref_id = item.ref.id if isinstance(item, Link) else item.id
            if ref_id in seen:
                raise ValidationError(
                    message="duplicate Project reference in ProjectGroup",
                    duplicate_id=ref_id,
                )
            seen.add(ref_id)
        return value


class ProjectGroupIn(BaseModel):
    """User-supplied fields for creating a project group"""

    model_config = ConfigDict(extra="forbid")

    name: SearchStr = Field(max_length=50)
    owner: PrefixedEmail
    description: str = Field(max_length=100)
    is_public: bool = False
    projects: list[ShortStr] = Field(default_factory=list)


class ProjectGroupOut(DocumentOut[PydanticObjectId]):
    name: SearchStr | None = None
    owner: PrefixedEmail | None = None
    is_public: bool | None = None
    projects: list[Link[Project]] | None = None
    description: str | None = None

    @staticmethod
    def default_fields() -> list[str]:
        return [
            "name",
            "description",
            "projects",
        ]


class ProjectGroupPatch(SparseFieldsModel):
    name: SearchStr | None = None
    owner: PrefixedEmail | None = None
    is_public: bool | None = None
    projects: list[Link[Project]] | None = None
    description: str | None = None


class ProjectRefs(BaseModel):
    """Request body for adding/removing projects from a group: the project ids to (un)link."""

    project_ids: list[ShortStr] = Field(default_factory=list)


class ProjectGroupFilter(BaseFilter):
    id: PydanticObjectId | None = None
    id__in: list[PydanticObjectId] | None = None
    id__neq: PydanticObjectId | None = None

    name: SearchStr | None = None
    name__in: list[SearchStr] | None = None
    name__neq: ShortStr | None = None

    owner: PrefixedEmail | None = None
    owner__in: list[PrefixedEmail] | None = None
    owner__neq: PrefixedEmail | None = None

    is_public: bool | None = None

    order_by: list[str] | None = None

    class Constants(BaseFilter.Constants):
        model: ProjectGroup

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
