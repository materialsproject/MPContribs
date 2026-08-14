from typing import Any

from beanie import UpdateResponse
from beanie.operators import Set

from mpcontribs_api.authz import User
from mpcontribs_api.domains._shared.repository import MongoDbRepository
from mpcontribs_api.domains.consumers.models import (
    Consumer,
    ConsumerFilter,
    ConsumerIn,
    ConsumerOut,
    ConsumerPatch,
)
from mpcontribs_api.exceptions import ConflictError, NotFoundError
from mpcontribs_api.pagination import CursorParams


class MongoDbConsumerRepository(MongoDbRepository[Consumer, ConsumerIn, ConsumerOut, ConsumerFilter, ConsumerPatch]):
    """Repository for admin-managed consumer overrides.

    Consumer overrides are an admin-only resource: every route that reaches this repository is
    gated by ``require_admin``, so no per-user read scope is needed and ``_build_scope`` returns an
    empty filter (admins see all overrides).
    """

    document_model = Consumer
    out_model = ConsumerOut

    @staticmethod
    def _build_scope(user: User) -> dict[str, Any]:
        # Admin-only resource (routes enforce ``require_admin``); no visibility filter required.
        return {}

    async def get_consumers(
        self,
        filter: ConsumerFilter,
        pagination: CursorParams,
        fields: frozenset[str] | None,
    ):
        """List consumer overrides. See ``get_many``."""
        return await self.get_many(pagination=pagination, filter=filter, fields=fields)

    async def get_consumer_by_id(self, id: str, fields: frozenset[str] | None):
        """Find a single consumer override by its document id. See ``get_by_id``."""
        return await self.get_by_id(self._convert_object_id(id), fields)

    async def get_by_consumer_id(self, consumer_id: str) -> Consumer | None:
        """Return the override document for a Kong ``consumer_id``, or ``None`` if none exists."""
        return await Consumer.find_one(Consumer.consumer_id == consumer_id)

    async def insert_consumer(self, consumer: ConsumerIn) -> Consumer:
        """Insert a new override, rejecting a duplicate ``consumer_id`` with a clean 409.

        The unique index on ``consumer_id`` is the hard guarantee; this pre-check turns the common
        case into a readable conflict instead of a raw driver error.
        """
        existing = await self.get_by_consumer_id(consumer.consumer_id)
        if existing is not None:
            raise ConflictError(
                "An override for this consumer already exists",
                consumer_id=consumer.consumer_id,
            )
        return await self.insert_one(consumer)

    async def patch_consumer_by_id(self, id: str, update: ConsumerPatch) -> Consumer:
        """Partially update an override's limits by document id.

        The limits live under a nested ``settings`` sub-document; the update is flattened to dotted
        ``settings.<field>`` keys so a partial patch changes only the named limits and leaves the
        siblings intact (a plain ``$set`` of ``settings`` would replace the whole sub-document).
        """
        object_id = self._convert_object_id(id)
        overrides = update.settings.model_dump(exclude_unset=True) if update.settings else {}
        dotted = {f"settings.{field}": value for field, value in overrides.items()}
        if not dotted:
            # Empty patch is a no-op that still returns the existing document (consistent behavior).
            existing = await Consumer.find_one(Consumer.id == object_id)
            if existing is None:
                raise NotFoundError(self._not_found(id))
            return existing

        updated = await Consumer.find_one(Consumer.id == object_id).update(
            Set(dotted),
            response_type=UpdateResponse.NEW_DOCUMENT,
        )  # pyright: ignore[reportGeneralTypeIssues] # beanie UpdateQuery is awaitable, but pyright doesn't see it
        if updated is None:
            raise NotFoundError(self._not_found(id))
        return updated

    async def delete_consumer_by_id(self, id: str) -> None:
        """Delete an override by document id. See ``delete_by_id``."""
        await self.delete_by_id(self._convert_object_id(id))
