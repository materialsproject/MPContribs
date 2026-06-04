import asyncio
from typing import Any, Literal

from beanie import UpdateResponse
from beanie.operators import Set

from mpcontribs_api.auth import User
from mpcontribs_api.domains._shared.repository import MongoDbRepository
from mpcontribs_api.domains.contributions.models import (
    Contribution,
    ContributionFilter,
    ContributionIn,
    ContributionOut,
    ContributionPatch,
)
from mpcontribs_api.pagination import CursorParams


class MongoDbContributionRepository(
    MongoDbRepository[Contribution, ContributionIn, ContributionOut, ContributionFilter, ContributionPatch]
):
    """A repository layer for access to MongoDB.

    Shared CRUD logic lives on :class:`MongoDbRepository`; the methods here are domain-named
    forwarders that give routers a consistent vocabulary and concrete types, plus the operations
    whose shape is genuinely contribution-specific (filtered delete, bulk insert, compound-key and
    id-keyed upsert, download).
    """

    document_model = Contribution
    out_model = ContributionOut

    @staticmethod
    def _build_scope(user: User) -> dict[str, Any]:
        """Provides scope based on current user's permitted groups and publicly released data."""
        if user.is_admin:
            return {}
        ors: list[dict[str, Any]] = [{"is_public": True}]
        if not user.is_anonymous:
            if user.groups:
                ors.append({"_id": {"$in": sorted(user.groups)}})
        return {"$or": ors}

    async def get_contributions(
        self,
        pagination: CursorParams,
        filter: ContributionFilter,
        fields: frozenset[str] | None,
    ):
        """Query the Contribution collection, scoped to the current user. See ``get_many``."""
        return await self.get_many(pagination=pagination, filter=filter, fields=fields)

    async def get_contribution_by_id(self, id: str, fields: frozenset[str] | None):
        """Find a single contribution by id, scoped to the current user. See ``get_by_id``."""
        return await self.get_by_id(id, fields)

    async def patch_contribution_by_id(self, id: str, update: ContributionPatch):
        """Partially update a contribution by id, scoped to the current user. See ``patch``."""
        return await self.patch(id, update)

    async def delete_contribution_by_id(self, id: str) -> None:
        """Delete a contribution by id, scoped to the current user. See ``delete_by_id``."""
        await self.delete_by_id(id)

    async def delete_contributions(self, filter: ContributionFilter):
        """Bulk deletion of Contributions described by the filter

        Args:
            filter (ContribtionFilter): the filter to use to identify contributions to delete
        """
        docs = filter.filter(self.document_model.find(self._scope))
        await docs.delete()

    async def insert_contributions(self, contributions: list[ContributionIn]):
        """Bulk insertion of Contributions

        Args:
            contributions (list[ContributionIn]): the list of contributions to be inserted

        Returns:
            list[ContributionOut]: the inserted documents
        """
        full_docs = [self.document_model.from_input_model(contrib) for contrib in contributions]
        # ordered=False lets Mongo keep inserting if a document fails
        return await self.document_model.insert_many(full_docs, ordered=False)

    async def upsert_contributions(self, contributions: list[ContributionIn]):
        """Upserts contributions.

        For each Contribution, if Contribution with identical identifiers exist, update, otherwise insert

        Args:
            contributions (list[ContributionIn]): the list of contributions to be upserted

        Returns:
            list[ContributionOut]: the list of upserted documents
        """

        # Handles upserting a document - no upsert_many command
        async def _upsert(contrib: ContributionIn):
            existing = await self.document_model.find_one(
                self._scope,
                self.document_model.project == contrib.project,
                self.document_model.identifier == contrib.identifier,
            )
            doc = self.document_model.from_input_model(contrib)
            # Update
            if existing is not None:
                update_data = doc.model_dump(exclude={"id"}, exclude_none=True)
                await existing.update(Set(update_data))
                return existing
            # Insert
            await doc.insert()
            return doc

        # Asynchronously run upsert on each contribution
        return await asyncio.gather(*[_upsert(c) for c in contributions])

    async def upsert_contribution_by_id(self, id: str, contribution: ContributionIn):
        """Upserts a single Contribution.

        If Contributions with identical identifiers exist, update, otherwise insert

        Args:
            id (str): the id of the Contribution to upsert
            contribution (ContributionIn): the Contribution to be upserted

        Returns:
            ContributionOut: the upserted document"""
        doc = self.document_model.from_input_model(contribution)
        return self.document_model.find_one(
            self._scope,
            self.document_model.id == id,
        ).upsert(
            Set(doc.model_dump(exclude={"id"}, exclude_none=True)),
            on_insert=doc,
            response_type=UpdateResponse.NEW_DOCUMENT,
        )

    async def download_contributions(
        self,
        format: Literal["json", "csv", "parquet"],
        filter: ContributionFilter,
        fields: frozenset[str] | None,
    ):
        pass
