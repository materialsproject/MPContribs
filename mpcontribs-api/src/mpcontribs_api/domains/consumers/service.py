from mpcontribs_api.domains.consumers.models import Consumer, ConsumerFilter, ConsumerIn, ConsumerOut, ConsumerPatch
from mpcontribs_api.domains.consumers.repository import MongoDbConsumerRepository
from mpcontribs_api.pagination import CursorParams, Page


class ConsumerService:
    def __init__(self, consumer: MongoDbConsumerRepository):
        self._consumer = consumer

    async def get_many(
        self, filter: ConsumerFilter, pagination: CursorParams, fields: frozenset[str] | None
    ) -> Page[ConsumerOut]:
        return await self._consumer.get_many(filter=filter, pagination=pagination, fields=fields)

    async def get_one(self, id: str, fields: frozenset[str] | None) -> ConsumerOut | None:
        return await self._consumer.get_one(identifiers={"id": id}, fields=fields)

    async def insert_one(self, consumer: ConsumerIn) -> Consumer:
        document = self._consumer.document_model.from_input_model(consumer)
        return await self._consumer.insert_one(document)

    async def patch_one(self, id: str, update: ConsumerPatch) -> Consumer:
        return await self._consumer.patch_one(identifiers={"id": id}, update=update)

    async def delete_one(self, id: str) -> None:
        await self._consumer.delete_one(identifiers={"id": id})
