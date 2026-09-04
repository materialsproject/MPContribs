from typing import ClassVar

from beanie import PydanticObjectId
from fastapi_filter import FilterDepends, with_prefix
from pydantic import BaseModel, Field

from mpcontribs_api.config import (
    ConsumerLimits,
)
from mpcontribs_api.domains._shared.filters import BaseFilter
from mpcontribs_api.domains._shared.models import BaseDocumentWithInput, DocumentOut
from mpcontribs_api.domains._shared.types import Identity


class ConsumerIdentity(Identity):
    """A consumer override's identity: Kong's unique ``consumer_id``."""

    consumer_id: str


class ConsumerProjectSettings(BaseModel):
    """Sparse per-consumer project overrides — an unset (``None``) field inherits the global default."""

    max_projects: int | None = Field(default=None, ge=0)
    max_columns: int | None = Field(default=None, ge=0)


class ConsumerContributionSettings(BaseModel):
    """Sparse per-consumer contribution overrides — an unset (``None``) field inherits the global default."""

    max_per_unapproved_project: int | None = Field(default=None, ge=0)
    max_components: int | None = Field(default=None, ge=0)
    max_data_depth: int | None = Field(default=None, ge=0)


class ConsumerInitiativeSettings(BaseModel):
    """Sparse per-consumer initiative overrides — an unset (``None``) field inherits the global default."""

    max_unapproved_per_owner: int | None = Field(default=None, ge=0)
    max_projects_per_unapproved: int | None = Field(default=None, ge=0)


# uses generic `T` to resolve type-checking
def _merge_domain[T: BaseModel](override: BaseModel | None, default: T) -> T:
    """Return ``default`` with each explicitly-set (non-``None``) leaf of ``override`` applied."""
    if override is None:
        return default
    return default.model_copy(update=override.model_dump(exclude_none=True))


class ConsumerSettings(BaseModel):
    """A per-consumer override of the global quota limits — sparse and domain-grouped.

    Only the limits an admin explicitly sets are stored; every unset field (``None``, and whole unset
    domains) inherits the current env-backed global default at resolve time (see :meth:`resolve`).
    Nothing is snapshotted, so an unset limit always tracks the live global rather than freezing at
    creation. The repository patches only the set leaves (``settings.<domain>.<leaf>``) via
    ``exclude_unset``, keeping a partial override partial.
    """

    project: ConsumerProjectSettings | None = None
    contribution: ConsumerContributionSettings | None = None
    initiative: ConsumerInitiativeSettings | None = None

    def resolve(self, defaults: ConsumerLimits) -> ConsumerLimits:
        """Merge this sparse override onto ``defaults``, returning fully-resolved concrete limits."""
        return ConsumerLimits(
            project=_merge_domain(self.project, defaults.project),
            contribution=_merge_domain(self.contribution, defaults.contribution),
            initiative=_merge_domain(self.initiative, defaults.initiative),
        )


class ConsumerProjectSettingsFilter(BaseFilter):
    max_projects: int | None = None
    max_projects__gte: int | None = None
    max_projects__lte: int | None = None

    max_columns: int | None = None
    max_columns__gte: int | None = None
    max_columns__lte: int | None = None

    order_by: list[str] | None = None


class ConsumerContributionSettingsFilter(BaseFilter):
    max_per_unapproved_project: int | None = None
    max_per_unapproved_project__gte: int | None = None
    max_per_unapproved_project__lte: int | None = None

    max_components: int | None = None
    max_components__gte: int | None = None
    max_components__lte: int | None = None

    max_data_depth: int | None = None
    max_data_depth__gte: int | None = None
    max_data_depth__lte: int | None = None

    order_by: list[str] | None = None


class ConsumerInitiativeSettingsFilter(BaseFilter):
    max_unapproved_per_owner: int | None = None
    max_unapproved_per_owner__gte: int | None = None
    max_unapproved_per_owner__lte: int | None = None

    max_projects_per_unapproved: int | None = None
    max_projects_per_unapproved__gte: int | None = None
    max_projects_per_unapproved__lte: int | None = None

    order_by: list[str] | None = None


class ConsumerSettingsFilter(BaseFilter):
    # The stored limits are domain-grouped under ``settings.<domain>.<leaf>``; nested prefixes keep
    # the built Mongo keys aligned with that shape.
    project: ConsumerProjectSettingsFilter | None = FilterDepends(with_prefix("project", ConsumerProjectSettingsFilter))
    contribution: ConsumerContributionSettingsFilter | None = FilterDepends(
        with_prefix("contribution", ConsumerContributionSettingsFilter)
    )
    initiative: ConsumerInitiativeSettingsFilter | None = FilterDepends(
        with_prefix("initiative", ConsumerInitiativeSettingsFilter)
    )

    # sorting
    order_by: list[str] | None = None


class Consumer(BaseDocumentWithInput[PydanticObjectId]):
    """Admin-managed, per-consumer overrides of the global quota limits.

    Stored in ``mp_consumers`` and matched to a request by Kong's ``consumer_id``. The overrides live
    under ``settings``, domain-grouped (``project``/``contribution``/``initiative``), and are sparse:
    only the limits an admin explicitly set are stored (``keep_nulls = False`` drops the rest). Every
    unset limit inherits the current env-backed global at resolve time, so it always tracks the live
    default rather than a value frozen at creation.
    """

    identity_model: ClassVar[type[Identity]] = ConsumerIdentity
    consumer_id: str
    settings: ConsumerSettings = Field(default_factory=ConsumerSettings)

    @classmethod
    def with_defaults(cls, consumer_id: str = "") -> Consumer:
        """In-memory Consumer that overrides nothing (every limit inherits the global default).

        Never persisted; a throwaway ``_id`` is minted only to satisfy the document's required id.
        """
        return cls.model_validate({"_id": PydanticObjectId(), "consumer_id": consumer_id})

    @classmethod
    def from_input_model(cls, data: ConsumerIn) -> Consumer:
        """Build a stored document from an input payload, minting a fresh server-owned ``_id``.

        The override is stored sparse — only the limits the admin supplied are persisted; unset ones
        are resolved against the global default on read, never snapshotted here.
        """
        settings = data.settings if data.settings is not None else ConsumerSettings()
        return cls.model_validate({"_id": PydanticObjectId(), "consumer_id": data.consumer_id, "settings": settings})

    class Settings:
        name = "mp_consumers"
        keep_nulls = False
        indexes = [ConsumerIdentity.index_model(name="consumer_id")]


class ConsumerIn(BaseModel):
    """Admin-supplied payload to create a consumer override.

    Limits left unset inherit the env-backed global defaults.
    """

    consumer_id: str
    settings: ConsumerSettings | None = None


class ConsumerPatch(BaseModel):
    """Partial update to a consumer override.

    Only the limits present under ``settings`` are changed; the rest are left as stored.
    """

    settings: ConsumerSettings | None = None


class ConsumerOut(DocumentOut[PydanticObjectId]):
    """Public-facing representation of a consumer override."""

    consumer_id: str | None = None
    settings: ConsumerSettings | None = None

    @staticmethod
    def default_fields() -> tuple[str, ...]:
        return tuple(ConsumerOut.model_fields)


class ConsumerFilter(BaseFilter):
    """Filter fields allowed when listing consumer overrides.

    The quota limits live under ``settings`` on the document, so the flat filter names here are
    remapped to dotted ``settings.<field>`` Mongo keys in ``_get_filter_conditions``.
    """

    id: PydanticObjectId | None = None
    id__in: list[PydanticObjectId] | None = None

    consumer_id: str | None = None
    consumer_id__in: list[str] | None = None

    settings: ConsumerSettingsFilter | None = FilterDepends(with_prefix("settings", ConsumerSettingsFilter))

    # sorting
    order_by: list[str] | None = None

    class Constants(BaseFilter.Constants):
        model = Consumer
