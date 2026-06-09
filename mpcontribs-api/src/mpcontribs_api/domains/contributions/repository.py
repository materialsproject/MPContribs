from typing import Any, Literal

from beanie import UpdateResponse
from beanie.operators import Set
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.results import DeleteResult

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
    whose shape is genuinely contribution-specific (filtered delete, id-keyed upsert, download).
    Multi-collection orchestration (component inserts) lives in ``ContributionService``.
    """

    document_model = Contribution
    out_model = ContributionOut

    def __init__(self, user: User) -> None:
        super().__init__(user)
        self._user = user

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
        filter: ContributionFilter,
        pagination: CursorParams | None = None,
        fields: frozenset[str] | None = None,
    ):
        """Query the Contribution collection, scoped to the current user. See ``get_many``."""
        return await self.get_many(pagination=pagination, filter=filter, fields=fields)

    async def get_contribution_by_id(self, id: str, fields: frozenset[str] | None):
        """Find a single contribution by id, scoped to the current user. See ``get_by_id``."""
        return await self.get_by_id(self._convert_object_id(id), fields)

    async def patch_contribution_by_id(self, id: str, update: ContributionPatch):
        """Partially update a contribution by id, scoped to the current user. See ``patch``."""
        return await self.patch(self._convert_object_id(id), update)

    async def delete_contribution_by_id(self, id: str) -> None:
        """Delete a contribution by id, scoped to the current user. See ``delete_by_id``."""
        await self.delete_by_id(self._convert_object_id(id))

    async def delete_contributions(
        self,
        filter: ContributionFilter,
    ) -> DeleteResult | None:
        """Bulk deletion of Contributions described by the filter.

        Args:
            filter (ContribtionFilter): the filter to use to identify contributions to delete
        """
        return await filter.filter(self.document_model.find(self._scope)).delete_many()

    async def insert_many_contributions(
        self,
        docs: list[Contribution],
        session: AsyncClientSession | None = None,
    ):
        """Bulk-insert pre-built Contribution documents.

        Used by the ``ContributionService`` no-component fast path. On partial failure pymongo
        raises ``BulkWriteError`` whose ``details["writeErrors"]`` carries per-index error info
        that the service maps back into a ``BulkWriteSummary``.
        """
        return await self.document_model.insert_many(docs, ordered=False, session=session)

    async def insert_contribution(
        self,
        doc: Contribution,
        session: AsyncClientSession | None = None,
    ) -> Contribution:
        """Insert a single pre-built Contribution document, optionally in a transaction."""
        await doc.insert(session=session)
        return doc

    async def find_one_contribution(self, project: str, identifier: str) -> Contribution | None:
        """Find a single contribution by (project, identifier), scoped to the current user."""
        return await self.document_model.find_one(
            self._scope,
            self.document_model.project == project,
            self.document_model.identifier == identifier,
        )

    async def update_contribution(self, doc: Contribution, update_data: dict[str, Any]) -> None:
        """Apply a partial update to an existing Contribution document."""
        await doc.update(Set(update_data))

    async def upsert_contribution_by_identifiers(
        self,
        identifiers: dict[str, str],
        contribution: ContributionIn,
    ) -> Contribution:
        """Atomically upsert a Contribution by its identifying fields.

        Relies on the unique index over those fields so that concurrent requests targeting the
        same key cannot both win the insert branch. Fields the caller did not set are not touched
        (partial update). On insert a fresh Contribution document is written with ``is_public=False``.

        Args:
            identifiers: the fields ContributionIn.identifiers() returns (project, identifier)
            contribution: the input payload to upsert

        Returns:
            Contribution: the document as it stands after the operation
        """
        doc = self.document_model.from_input_model(contribution)
        update_data = doc.model_dump(exclude={"id"}, exclude_none=True)
        query = self.document_model.find_one(
            self._scope,
            self.document_model.project == identifiers["project"],
            self.document_model.identifier == identifiers["identifier"],
        ).upsert(
            Set(update_data),
            on_insert=doc,
            response_type=UpdateResponse.NEW_DOCUMENT,
        )
        return await query  # pyright: ignore[reportGeneralTypeIssues] # beanie UpdateQuery is awaitable, but pyright doesn't see it

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
            self.document_model.id == self._convert_object_id(id),
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
