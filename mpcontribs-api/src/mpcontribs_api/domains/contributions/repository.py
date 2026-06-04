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
from mpcontribs_api.exceptions import NotFoundError
from mpcontribs_api.pagination import CursorParams


class MongoDbContributionRepository(MongoDbRepository[Contribution, ContributionIn, ContributionOut]):
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
        return await self.get_many(pagination=pagination, filter=filter, fields=fields)

    async def delete_contributions(self, filter: ContributionFilter):
        docs = filter.filter(self.document_model.find(self._scope))
        await docs.delete()

    async def insert_contributions(self, contributions: list[ContributionIn]):
        full_docs = [self.document_model.from_input_model(contrib) for contrib in contributions]
        # ordered=False lets Mongo keep inserting if a document fails
        return await self.document_model.insert_many(full_docs, ordered=False)

    async def upsert_contributions(self, contributions: list[ContributionIn]):
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

    async def download_contributions(
        self,
        format: Literal["json", "csv", "parquet"],
        filter: ContributionFilter,
        fields: frozenset[str] | None,
    ):
        pass

    async def delete_contribution_by_id(self, id: str):
        await self.document_model.find_one(self._scope, self.document_model.id == id).delete()

    async def get_contribution_by_id(self, id: str, fields: frozenset[str] | None):
        return await self.document_model.find_one(
            self._scope,
            self.document_model.id == id,
            projection_model=self.out_model.projection(fields),
        )

    async def upsert_contribution_by_id(self, id: str, contribution: ContributionIn):
        doc = self.document_model.from_input_model(contribution)
        return self.document_model.find_one(
            self._scope,
            self.document_model.id == id,
        ).upsert(
            Set(doc.model_dump(exclude={"id"}, exclude_none=True)),
            on_insert=doc,
            response_type=UpdateResponse.NEW_DOCUMENT,
        )

    async def update_contribution_by_id(self, id: str, update: ContributionPatch):
        # Only retain set fields (patch)
        update_data = update.model_dump(exclude_unset=True)
        # If update is empty, return the model anyways (consistent behavior)
        if not update_data:
            existing = await self.document_model.get(id)
            if existing is None:
                raise NotFoundError(f"Contribution with id {id} not found")
            return existing

        # Otherwise, update the fields fully (set)
        # Brendan TODO: Set will replace an entire field
        # - if we want to append to a list (ie. add a reference) we ned Push/AddToSet
        query = self.document_model.find_one(self.document_model.id == id).update(
            Set(update_data),
            response_type=UpdateResponse.NEW_DOCUMENT,
        )
        updated = await query  # pyright: ignore[reportGeneralTypeIssues] # beanie UpdateQuery is awaitable, but pyright doesn't see it
        if updated is None:
            raise NotFoundError(f"Contribution with id {id} not found")
        return updated
