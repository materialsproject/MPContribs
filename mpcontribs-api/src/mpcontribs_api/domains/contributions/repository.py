import asyncio
from typing import Any, Literal, cast

from beanie import Link, UpdateResponse
from beanie.operators import Set

from mpcontribs_api.auth import User
from mpcontribs_api.domains._shared.repository import MongoDbRepository
from mpcontribs_api.domains.attachments.models import Attachment, AttachmentIn
from mpcontribs_api.domains.attachments.repository import MongoDbAttachmentRepository
from mpcontribs_api.domains.contributions.models import (
    Contribution,
    ContributionFilter,
    ContributionIn,
    ContributionOut,
    ContributionPatch,
)
from mpcontribs_api.domains.structures.models import Structure, StructureIn
from mpcontribs_api.domains.structures.repository import MongoDbStructureRepository
from mpcontribs_api.domains.tables.models import Table, TableIn
from mpcontribs_api.domains.tables.repository import MongoDbTableRepository
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
        pagination: CursorParams,
        filter: ContributionFilter,
        fields: frozenset[str] | None,
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

    async def delete_contributions(self, filter: ContributionFilter):
        """Bulk deletion of Contributions described by the filter

        Args:
            filter (ContribtionFilter): the filter to use to identify contributions to delete
        """
        docs = filter.filter(self.document_model.find(self._scope))
        await docs.delete()

    async def _insert_components(
        self,
        contributions: list[ContributionIn],
    ) -> tuple[list[Structure], list[Table], list[Attachment], list[slice], list[slice], list[slice]]:
        """Bulk-insert component documents for a batch and return per-contribution slices.

        Returns:
            (structures, tables, attachments, struct_slices, table_slices, attach_slices)
            where slice[i] selects the components belonging to contributions[i].
        """
        all_structures: list[StructureIn] = []
        all_tables: list[TableIn] = []
        all_attachments: list[AttachmentIn] = []
        struct_slices: list[slice] = []
        table_slices: list[slice] = []
        attach_slices: list[slice] = []

        for contrib in contributions:
            s0 = len(all_structures)
            all_structures.extend(contrib.structures or [])
            struct_slices.append(slice(s0, len(all_structures)))

            t0 = len(all_tables)
            all_tables.extend(contrib.tables or [])
            table_slices.append(slice(t0, len(all_tables)))

            a0 = len(all_attachments)
            all_attachments.extend(contrib.attachments or [])
            attach_slices.append(slice(a0, len(all_attachments)))

        structures = await MongoDbStructureRepository(self._user).insert_structures(all_structures)
        tables = await MongoDbTableRepository(self._user).insert_tables(all_tables)
        attachments = await MongoDbAttachmentRepository(self._user).insert_attachments(all_attachments)

        return structures, tables, attachments, struct_slices, table_slices, attach_slices

    async def insert_contributions(self, contributions: list[ContributionIn]):
        """Bulk insertion of Contributions.

        Component documents (structures, tables, attachments) embedded in each ContributionIn are
        bulk-inserted first; the resulting IDs are then stored as Links on the Contribution before
        the contributions themselves are bulk-inserted.

        Args:
            contributions (list[ContributionIn]): the list of contributions to be inserted

        Returns:
            list[ContributionOut]: the inserted documents
        """
        structures, tables, attachments, struct_slices, table_slices, attach_slices = (
            await self._insert_components(contributions)
        )

        full_docs: list[Contribution] = []
        for i, contrib in enumerate(contributions):
            doc = self.document_model.from_input_model(contrib)
            doc.structures = cast(list[Link[Structure]] | None, structures[struct_slices[i]] or None)
            doc.tables = cast(list[Link[Table]] | None, tables[table_slices[i]] or None)
            doc.attachments = cast(list[Link[Attachment]] | None, attachments[attach_slices[i]] or None)
            full_docs.append(doc)

        return await self.document_model.insert_many(full_docs, ordered=False)

    async def upsert_contributions(self, contributions: list[ContributionIn]):
        """Upserts contributions.

        Component documents are bulk-inserted first (same as insert_contributions), then each
        Contribution is upserted by (project, identifier).

        Args:
            contributions (list[ContributionIn]): the list of contributions to be upserted

        Returns:
            list[ContributionOut]: the list of upserted documents
        """
        structures, tables, attachments, struct_slices, table_slices, attach_slices = (
            await self._insert_components(contributions)
        )

        async def _upsert(contrib: ContributionIn, i: int):
            existing = await self.document_model.find_one(
                self._scope,
                self.document_model.project == contrib.project,
                self.document_model.identifier == contrib.identifier,
            )
            doc = self.document_model.from_input_model(contrib)
            doc.structures = cast(list[Link[Structure]] | None, structures[struct_slices[i]] or None)
            doc.tables = cast(list[Link[Table]] | None, tables[table_slices[i]] or None)
            doc.attachments = cast(list[Link[Attachment]] | None, attachments[attach_slices[i]] or None)
            if existing is not None:
                update_data = doc.model_dump(exclude={"id"}, exclude_none=True)
                await existing.update(Set(update_data))
                return existing
            await doc.insert()
            return doc

        return await asyncio.gather(*[_upsert(c, i) for i, c in enumerate(contributions)])

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
