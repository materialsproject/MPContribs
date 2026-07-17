from __future__ import annotations

from typing import Self

from beanie import PydanticObjectId
from bson.errors import InvalidId
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pymongo import ASCENDING, IndexModel

from mpcontribs_api.domains._shared.filters import BaseFilter
from mpcontribs_api.domains._shared.models import BaseDocumentWithInput, DocumentOut
from mpcontribs_api.domains._shared.types import NFKCStr, PrefixedEmail, Slug
from mpcontribs_api.exceptions import ValidationError
from mpcontribs_api.projection import SparseFieldsModel


class Initiative(BaseDocumentWithInput[PydanticObjectId]):
    """A canonical, authoritative grouping of projects into a larger organizational effort.

    Unlike an ad-hoc ``ProjectGroup`` (many-to-many, user-curated), an initiative is the single
    canonical parent of its member projects: a project points at *at most one* initiative via
    ``Project.initiative``. Membership is therefore derived from the projects collection — an
    initiative stores no project list of its own.

    Collaborator rights are drawn from the caller's roles, mirroring how projects use groups: a
    user may manage an initiative (add projects, patch it) if they own it, are an admin, or carry
    the ``initiative:<slug>`` role.
    """

    slug: Slug
    name: NFKCStr = Field(max_length=100)
    owner: PrefixedEmail
    is_public: bool = False
    is_approved: bool = False

    class Settings:
        name = "initiatives"
        keep_nulls = False
        indexes = [
            IndexModel(keys=[("slug", ASCENDING)], name="slug", unique=True),
            IndexModel(
                keys=[("owner", ASCENDING), ("is_approved", ASCENDING), ("is_public", ASCENDING)],
                name="owner_is_approved_is_public",
            ),
        ]
        validate_on_save = True

    @classmethod
    def identifier_fields(cls) -> frozenset[str]:
        """An ``Initiative`` is uniquely identified by its globally-unique ``slug``."""
        return frozenset({"slug"})

    @model_validator(mode="after")
    def _public_requires_approved(self) -> Self:
        """An initiative cannot be public until it has been approved."""
        if self.is_public and not self.is_approved:
            raise ValidationError("an initiative cannot be public until it is approved", slug=self.slug)
        return self


class InitiativeIn(BaseModel):
    """User-supplied fields for creating an initiative.

    ``owner`` is forced to the caller and ``is_public`` / ``is_approved`` always start ``False``
    (an admin approves later), so none of them are part of the input contract.
    """

    model_config = ConfigDict(extra="forbid")

    slug: Slug
    name: NFKCStr = Field(max_length=100)


class InitiativeOut(DocumentOut[PydanticObjectId]):
    slug: Slug | None = None
    name: NFKCStr | None = None
    owner: PrefixedEmail | None = None
    is_public: bool | None = None
    is_approved: bool | None = None

    @staticmethod
    def default_fields() -> list[str]:
        return ["slug", "name", "owner", "is_public", "is_approved"]


class InitiativePatch(SparseFieldsModel):
    """Partial update to an initiative.

    ``slug`` and ``owner`` are immutable and intentionally absent. ``is_approved`` is admin-only
    (enforced in the repository), and the ``is_public`` ⇒ ``is_approved`` invariant is re-checked
    there against the resulting state, since a partial ``$set`` bypasses the document validator.
    """

    name: NFKCStr | None = Field(default=None, max_length=100)
    is_public: bool | None = None
    is_approved: bool | None = None


class InitiativeFilter(BaseFilter):
    id: PydanticObjectId | None = None
    id__in: list[PydanticObjectId] | None = None
    id__neq: PydanticObjectId | None = None

    slug: Slug | None = None
    slug__in: list[Slug] | None = None
    slug__neq: Slug | None = None

    name: NFKCStr | None = None
    name__in: list[NFKCStr] | None = None
    name__neq: NFKCStr | None = None

    owner: PrefixedEmail | None = None
    owner__in: list[PrefixedEmail] | None = None
    owner__neq: PrefixedEmail | None = None

    is_public: bool | None = None
    is_approved: bool | None = None

    order_by: list[str] | None = None

    class Constants(BaseFilter.Constants):
        model = Initiative

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
