from typing import Any

from mpcontribs_api.config import ConsumerLimits, get_settings
from mpcontribs_api.domains.consumers.models import (
    ConsumerFilter,
    ConsumerIn,
    ConsumerOut,
    ConsumerPatch,
)
from mpcontribs_api.domains.consumers.repository import MongoDbConsumerRepository
from mpcontribs_api.exceptions import NotFoundError
from mpcontribs_api.pagination import CursorParams, Page


class ConsumerService:
    def __init__(self, consumer: MongoDbConsumerRepository):
        self._consumer = consumer

    async def effective_limits(self, consumer_id: str | None) -> ConsumerLimits:
        """Resolve the concrete limits in effect for a caller's Kong ``consumer_id``.

        Starts from the env-backed global defaults and merges the caller's stored (sparse) override
        on top, so every limit the admin did not set inherits the live global. A caller with no
        ``consumer_id`` (anonymous/dev) skips the lookup and gets the globals unchanged.
        """
        defaults = get_settings().consumer
        if consumer_id is None:
            return defaults
        try:
            override = await self._consumer.read_one({"consumer_id": consumer_id}, fields=None)
        except NotFoundError:
            # No stored override for this consumer: fall back to the global defaults.
            return defaults
        if override is None or override.settings is None:
            return defaults
        return override.settings.resolve(defaults)

    async def read_many(
        self, filter: ConsumerFilter, pagination: CursorParams, fields: frozenset[str] | None
    ) -> Page[ConsumerOut]:
        return await self._consumer.read_many(filter=filter, pagination=pagination, fields=fields)

    async def read_one(self, identifiers: dict[str, Any], fields: frozenset[str] | None) -> ConsumerOut:
        """Read one override by its identity — the bare ``{"id": ...}`` or ``{"consumer_id": ...}``; 404 if absent."""
        return await self._consumer.read_one(identifiers=identifiers, fields=fields)

    async def insert_one(self, consumer: ConsumerIn) -> ConsumerOut:
        document = self._consumer.document_model.from_input_model(consumer)
        doc = await self._consumer.insert_one(document)
        return ConsumerOut.model_validate(doc, from_attributes=True)

    async def update_one(self, identifiers: dict[str, Any], update: ConsumerPatch) -> ConsumerOut:
        doc = await self._consumer.update_one(identifiers=identifiers, update=update)
        return ConsumerOut.model_validate(doc, from_attributes=True)

    async def delete_one(self, identifiers: dict[str, Any]) -> None:
        await self._consumer.delete_one(identifiers=identifiers)
