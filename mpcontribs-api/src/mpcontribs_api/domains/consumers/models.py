from typing import ClassVar

from beanie import PydanticObjectId
from fastapi_filter import FilterDepends, with_prefix
from pydantic import BaseModel, Field

from mpcontribs_api.config import get_settings
from mpcontribs_api.domains._shared.filters import BaseFilter
from mpcontribs_api.domains._shared.models import BaseDocumentWithInput, DocumentOut
from mpcontribs_api.domains._shared.types import Identity


class ConsumerIdentity(Identity):
    """A consumer override's identity: Kong's unique ``consumer_id``."""

    consumer_id: str


class ConsumerProjectSettings(BaseModel):
    """Per-consumer project limits — effective, fully-resolved values."""

    max_projects: int = Field(default_factory=lambda: get_settings().consumer.project.max_projects, ge=0)
    max_columns: int = Field(default_factory=lambda: get_settings().consumer.project.max_columns, ge=0)


class ConsumerContributionSettings(BaseModel):
    """Per-consumer contribution limits — effective, fully-resolved values."""

    max_per_unapproved_project: int = Field(
        default_factory=lambda: get_settings().consumer.contribution.max_per_unapproved_project, ge=0
    )
    max_components: int = Field(default_factory=lambda: get_settings().consumer.contribution.max_components, ge=0)
    max_data_depth: int = Field(default_factory=lambda: get_settings().consumer.contribution.max_data_depth, ge=0)


class ConsumerInitiativeSettings(BaseModel):
    """Per-consumer initiative limits — effective, fully-resolved values."""

    max_unapproved_per_owner: int = Field(
        default_factory=lambda: get_settings().consumer.initiative.max_unapproved_per_owner, ge=0
    )
    max_projects_per_unapproved: int = Field(
        default_factory=lambda: get_settings().consumer.initiative.max_projects_per_unapproved, ge=0
    )


class ConsumerSettings(BaseModel):
    """Per-consumer settings — the effective, fully-resolved values read by the app.

    The quota limits are domain-grouped (``project``/``contribution``/``initiative``) and default
    directly from the env-backed ``config.QuotaLimits`` (so an unset field resolves to its global
    default). Because unset fields fall back to defaults, admins can supply only the fields they want
    to change (the repository/input paths use ``exclude_unset`` to keep an override partial).
    """

    project: ConsumerProjectSettings = Field(default_factory=ConsumerProjectSettings)
    contribution: ConsumerContributionSettings = Field(default_factory=ConsumerContributionSettings)
    initiative: ConsumerInitiativeSettings = Field(default_factory=ConsumerInitiativeSettings)


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

    Stored in ``mp_consumers`` and matched to a request by Kong's ``consumer_id``. The quota limits
    live under ``settings``, domain-grouped (``project``/``contribution``/``initiative``); an admin can
    override a single limit and any field they leave unset inherits the env-backed default,
    snapshotted onto the document at insert time.
    """

    identity_model: ClassVar[type[Identity]] = ConsumerIdentity
    consumer_id: str
    settings: ConsumerSettings = Field(default_factory=ConsumerSettings)

    @classmethod
    def with_defaults(cls, consumer_id: str = "") -> Consumer:
        """In-memory Consumer whose ``settings`` carry the env-backed default limits.

        Never persisted; a throwaway ``_id`` is minted only to satisfy the document's required id.
        """
        return cls.model_validate({"_id": PydanticObjectId(), "consumer_id": consumer_id})

    @classmethod
    def from_input_model(cls, data: ConsumerIn) -> Consumer:
        """Build a stored document from an input payload, minting a fresh server-owned ``_id``.

        Unset fields snapshot the current env defaults (``ConsumerSettings`` fills them from
        ``config.QuotaLimits``), so the stored document always carries fully-resolved values.
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
