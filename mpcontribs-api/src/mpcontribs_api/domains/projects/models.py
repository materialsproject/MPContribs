from enum import StrEnum
from typing import Any, ClassVar, Literal

from beanie import Link
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from mpcontribs_api import pagination
from mpcontribs_api.domains._shared.filters import BaseFilter
from mpcontribs_api.domains._shared.models import BaseDocumentWithInput, DocumentOut, Identity
from mpcontribs_api.domains._shared.types import CANONICAL_KEY_COERCION, PrefixedEmail, SearchStr, ShortStr
from mpcontribs_api.domains.initiatives.models import Initiative
from mpcontribs_api.exceptions import ValidationError


class ProjectIdentity(Identity):
    """A project's identity: its human-chosen short name, which is also its Mongo ``_id``.

    Because the identity is the primary key, no separate unique index is declared — Mongo's implicit
    ``_id`` index enforces it. (``index_model`` must not be added to ``Settings``: it would key on a
    literal ``"id"`` field that does not exist in the stored document.)
    """

    id: ShortStr


def _validate_unique_column(value: str | None) -> str | None:
    """Validate and canonicalize ``unique_column``: a non-empty, non-blank dotted path.

    ``unique_column`` is a path *into* ``Contribution.data``, so each segment is coerced through the
    same :data:`CANONICAL_KEY_COERCION` symbol as data keys.
    """
    if value is None:
        return None
    segments = value.split(".")
    if not value.strip() or any(not segment for segment in segments):
        raise ValidationError("unique_column must be a non-empty dotted path (no blank segments).", value=value)
    coerced = [CANONICAL_KEY_COERCION(segment) for segment in segments]
    if any(not segment for segment in coerced):
        raise ValidationError(
            "unique_column segments must not reduce to an empty string after canonical key coercion.", value=value
        )
    return ".".join(coerced)


def validate_column_limit(columns: Any, max_columns: int) -> None:
    """Reject a *write* carrying more columns than ``max_columns`` allows.

    Allows legacy docs that exceed cap to be returned without raising an error.
    """
    if isinstance(columns, list) and len(columns) > max_columns:
        raise ValidationError(
            f"columns cannot have more than {max_columns} entries",
            column_length=len(columns),
        )


class Column(BaseModel):
    path: str
    min: float | None = None
    max: float | None = None
    unit: str | None = None

    @property
    def segments(self) -> tuple[str, ...]:
        return tuple(self.path.split("."))


class Stats(BaseModel):
    columns: int = 0
    contributions: int = 0
    tables: int = 0
    structures: int = 0
    attachments: int = 0
    size: float = 0


class Reference(BaseModel):
    # TODO: Labels have some restrictions, not sure exactly what yet
    label: str
    url: HttpUrl


class ProjectTag(StrEnum):
    """Controlled vocabulary for tagging projects"""

    catalysis = "catalysis"
    batteries = "batteries"
    photovoltaics = "photovoltaics"
    thermoelectrics = "thermoelectrics"
    carbon_capture = "carbon_capture"
    superconductors = "superconductors"
    hydrogen_storage = "hydrogen_storage"
    fuel_cells = "fuel_cells"
    magnets = "magnets"
    coatings = "coatings"
    perovskites = "perovskites"
    mofs = "mofs"
    alloys = "alloys"
    two_d_materials = "two_d_materials"
    oxides = "oxides"
    polymers = "polymers"
    zeolites = "zeolites"
    high_entropy_alloys = "high_entropy_alloys"
    electronic_structure = "electronic_structure"
    thermodynamics = "thermodynamics"
    mechanical = "mechanical"
    magnetism = "magentism"
    dielectric = "dielectric"
    optical = "optical"
    phonons = "phonons"
    defects = "defects"
    surfaces = "surfaces"
    transport = "transport"
    dft = "dft"
    machine_learning = "machine_learning"
    experimental = "experimental"
    high_throughput = "high_throughput"
    spectroscopy = "spectroscopy"


class ProjectBase(BaseModel):
    title: ShortStr
    authors: str
    description: str
    owner: PrefixedEmail

    # The single data column (dotted path) that disambiguates contributions sharing the same
    # (material_id, chemical_system_id, formula). None -> that triple must be unique on its own. Its
    # value is promoted to Contribution.unique_value on write (see contributions.extract_unique_value).
    unique_column: str | None = None

    # Optional
    stats: Stats = Field(default_factory=Stats)
    tags: list[ProjectTag] | None = None
    mp_category: str | None = None
    references: list[Reference] = Field(default_factory=list)
    long_title: str | None = None
    other: dict[str, Any] = Field(default_factory=dict)
    is_public: bool = False
    is_approved: bool = False
    license: Literal["CCA4", "CCPD"] | None = None

    initiative: Link[Initiative] | None = None

    # Empty method for now. Keeping for business logic later
    # Validated on every representation (input and stored) so a bad unique_column is rejected immediately
    @field_validator("unique_column")
    @classmethod
    def _check_unique_column(cls, v: str | None) -> str | None:
        return _validate_unique_column(v)

    class Settings:
        name = "projects"
        keep_nulls = False


class Project(ProjectBase, BaseDocumentWithInput[ShortStr]):
    """Document model of what is actually stored."""

    identity_model: ClassVar[type[Identity]] = ProjectIdentity
    # Server-owned: derived from the project's contributions
    stats: Stats = Field(default_factory=Stats)
    columns: list[Column] = Field(default_factory=list)

    @classmethod
    def from_input_model(cls, data: ProjectIn, id: str) -> Project:  # pyright: ignore[reportIncompatibleMethodOverride]
        # ``id`` comes from the request path, not the body (see ``ProjectIn``). ``initiative`` is a
        # bare id/slug identifier on input (see ``ProjectIn.initiative``); it is resolved to a
        # ``Link`` by ``ProjectService`` and never flows straight into the document here.
        return cls(_id=id, **data.model_dump(exclude={"initiative"}))

    @staticmethod
    def decode_cursor(cursor: str) -> str:
        """Decodes cursor and returns it as a str.

        Needs to override the parent class since Project.id is a simple str
        """
        return pagination.decode_cursor(cursor)

    @classmethod
    def server_managed_fields(cls) -> tuple:
        return ("is_public", "is_approved", "stats", "mp_category")


class ProjectOut(DocumentOut[ShortStr]):
    """Full response of all public-facing fields."""

    model_config = ConfigDict(extra="ignore")
    authors: str | None = None
    description: str | None = None
    title: ShortStr | None = None
    tags: list[SearchStr] | None = None
    mp_category: str | None = None
    owner: PrefixedEmail | None = None
    other: dict[str, Any] | None = None
    is_public: bool | None = None
    is_approved: bool | None = None
    long_title: str | None = None
    unique_column: str | None = None
    references: list[Reference] | None = None
    stats: Stats | None = None
    columns: list[Column] | None = None
    license: Literal["CCA4", "CCPD"] | None = None
    initiative: Link[Initiative] | None = None

    @staticmethod
    def default_fields() -> tuple[str, ...]:
        return ("id", "is_public", "title", "owner", "is_approved", "unique_column")


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

    tags: list[SearchStr] | None = None  # exact match of list
    tags__in: list[SearchStr] | None = None  # if at least one tag is present
    tags__contains: list[SearchStr] | None = None  # Project.tags must be a superset of these

    mp_category: str | None = None
    mp_category__in: list[str] | None = None
    mp_category__neq: str | None = None
    mp_category__ilike: str | None = None

    # fuzzy only
    long_title__ilike: str | None = None

    is_public: bool | None = None
    is_approved: bool | None = None
    unique_column: str | None = None
    unique_column__neq: str | None = None

    license: Literal["CCA4", "CCPD"] | None = None
    license__in: list[Literal["CCA4", "CCPD"]] | None = None

    # sorting
    order_by: list[str] | None = None

    class Constants(BaseFilter.Constants):
        model = Project


# Left for namespace similarity between modules
class ProjectIn(ProjectBase):
    """User-supplied input for a project write.

    Carries no ``id`` (it comes from the request path) and no ``stats``/``columns`` (server-owned,
    recomputed from contributions). ``is_approved`` is accepted but only honored for admins.
    """

    # str here (id or slug), but ProjectService resolves it to a Link. Deliberately narrows the
    # inherited `Link[Initiative] | None` to a plain identifier that never reaches the document.
    initiative: str | None = None  # pyright: ignore[reportIncompatibleVariableOverride]


class ProjectPatch(BaseModel):
    """Nullable Project representation of user-supplied data for partial update (patch).

    ``stats`` and ``columns`` are intentionally absent: they are server-owned and recomputed from
    the project's contributions, never patched by a client. ``is_approved`` is accepted but the
    repository allows only admins to change it.
    """

    title: ShortStr | None = None
    authors: str | None = None
    description: str | None = None
    tags: list[SearchStr] | None = None
    owner: PrefixedEmail | None = None
    unique_column: str | None = None
    references: list[Reference] = Field(default_factory=list)
    long_title: str | None = None
    other: dict[str, Any] = Field(default_factory=dict)
    is_public: bool = False
    # None => unset (left unchanged); admin-only when set
    is_approved: bool | None = None
    license: Literal["CCA4", "CCPD"] | None = None

    # str here, but ProjectService coerces to a Link
    initiative: str | None = None

    @field_validator("unique_column")
    @classmethod
    def _check_unique_column(cls, v: str | None) -> str | None:
        return _validate_unique_column(v)
