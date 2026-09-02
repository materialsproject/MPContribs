from typing import Any

from mpcontribs_api.config import ConsumerLimits, get_settings
from mpcontribs_api.domains.consumers.models import (
    Consumer,
    ConsumerFilter,
    ConsumerIn,
    ConsumerOut,
    ConsumerPatch,
)
from mpcontribs_api.domains.consumers.repository import MongoDbConsumerRepository
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
        override = await self._consumer.read_one({"consumer_id": consumer_id}, fields=None)
        if override is None or override.settings is None:
            return defaults
        return override.settings.resolve(defaults)

    async def read_many(
        self, filter: ConsumerFilter, pagination: CursorParams, fields: frozenset[str] | None
    ) -> Page[ConsumerOut]:
        return await self._consumer.read_many(filter=filter, pagination=pagination, fields=fields)

    async def read_one(self, identifiers: dict[str, Any], fields: frozenset[str] | None) -> ConsumerOut | None:
        """Read one override by its identity — the bare ``{"id": ...}`` or ``{"consumer_id": ...}``."""
        return await self._consumer.read_one(identifiers=identifiers, fields=fields)

    async def insert_one(self, consumer: ConsumerIn) -> Consumer:
        document = self._consumer.document_model.from_input_model(consumer)
        return await self._consumer.insert_one(document)

    async def update_one(self, identifiers: dict[str, Any], update: ConsumerPatch) -> Consumer:
        return await self._consumer.update_one(identifiers=identifiers, update=update)

    async def delete_one(self, identifiers: dict[str, Any]) -> None:
        await self._consumer.delete_one(identifiers=identifiers)
