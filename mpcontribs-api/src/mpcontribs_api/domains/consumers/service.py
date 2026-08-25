from mpcontribs_api.domains.consumers.models import (
    Consumer,
    ConsumerFilter,
    ConsumerIn,
    ConsumerOut,
    ConsumerPatch,
    ConsumerSettings,
)
from mpcontribs_api.domains.consumers.repository import MongoDbConsumerRepository
from mpcontribs_api.pagination import CursorParams, Page


class ConsumerService:
    def __init__(self, consumer: MongoDbConsumerRepository):
        self._consumer = consumer

    async def effective_limits(self, consumer_id: str | None) -> ConsumerSettings:
        """Resolve the settings in effect for a caller's Kong ``consumer_id``.

        Returns the stored override's ``settings`` if one exists, otherwise a default
        ``ConsumerSettings`` (which fills from the env-backed global defaults). A caller with no
        ``consumer_id`` (anonymous/dev) skips the lookup entirely.
        """
        if consumer_id is None:
            return ConsumerSettings()
        override = await self._consumer.read_one({"consumer_id": consumer_id}, fields=None)
        return override.settings if override and override.settings else ConsumerSettings()

    async def read_many(
        self, filter: ConsumerFilter, pagination: CursorParams, fields: frozenset[str] | None
    ) -> Page[ConsumerOut]:
        return await self._consumer.read_many(filter=filter, pagination=pagination, fields=fields)

    async def read_one(self, id: str, fields: frozenset[str] | None) -> ConsumerOut | None:
        return await self._consumer.read_one(identifiers={"id": id}, fields=fields)

    async def insert_one(self, consumer: ConsumerIn) -> Consumer:
        document = self._consumer.document_model.from_input_model(consumer)
        return await self._consumer.insert_one(document)

    async def update_one(self, id: str, update: ConsumerPatch) -> Consumer:
        return await self._consumer.update_one(identifiers={"id": id}, update=update)

    async def delete_one(self, id: str) -> None:
        await self._consumer.delete_one(identifiers={"id": id})
