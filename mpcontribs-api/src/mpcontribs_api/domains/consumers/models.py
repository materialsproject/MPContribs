from beanie import PydanticObjectId
from fastapi_filter import FilterDepends, with_prefix
from pydantic import BaseModel, Field
from pymongo import ASCENDING, IndexModel

from mpcontribs_api.config import get_settings
from mpcontribs_api.domains._shared.filters import BaseFilter
from mpcontribs_api.domains._shared.models import BaseDocumentWithInput, DocumentOut


class ConsumerSettings(BaseModel):
    """Per-consumer settings — the effective, fully-resolved values read by the app.

    The quota limits default directly from the env-backed ``config.QuotaLimits`` (so an unset field
    resolves to its global default), and this model is free to grow settings beyond quota limits.
    Because unset fields fall back to defaults, admins can supply only the fields they want to change
    (the repository/input paths use ``exclude_unset`` to keep an override partial).
    """

    max_projects: int = Field(default_factory=lambda: get_settings().consumer.max_projects, ge=0)
    max_unapproved_contributions_per_project: int = Field(
        default_factory=lambda: get_settings().consumer.max_unapproved_contributions_per_project, ge=0
    )
    max_columns: int = Field(default_factory=lambda: get_settings().consumer.max_columns, ge=0)


class ConsumerSettingsFilter(BaseFilter):
    max_projects: int | None = None
    max_projects__gte: int | None = None
    max_projects__lte: int | None = None

    max_unapproved_contributions_per_project: int | None = None
    max_unapproved_contributions_per_project__gte: int | None = None
    max_unapproved_contributions_per_project__lte: int | None = None

    max_columns: int | None = None
    max_columns__gte: int | None = None
    max_columns__lte: int | None = None

    # sorting
    order_by: list[str] | None = None


class Consumer(BaseDocumentWithInput[PydanticObjectId]):
    """Admin-managed, per-consumer overrides of the global quota limits.

    Stored in ``mp_consumers`` and matched to a request by Kong's ``consumer_id``. The quota limits
    live under ``settings`` (a ``QuotaLimits``); an admin can override a single limit and any field
    they leave unset inherits the env-backed default, snapshotted onto the document at insert time.
    """

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
        indexes = [IndexModel([("consumer_id", ASCENDING)], name="consumer_id", unique=True)]


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
    def default_fields() -> list[str]:
        return [*ConsumerOut.model_fields]


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
