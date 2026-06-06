import asyncio
from typing import cast

from beanie import Link

from mpcontribs_api.domains.attachments.models import Attachment, AttachmentIn
from mpcontribs_api.domains.attachments.repository import MongoDbAttachmentRepository
from mpcontribs_api.domains.contributions.models import Contribution, ContributionIn
from mpcontribs_api.domains.contributions.repository import MongoDbContributionRepository
from mpcontribs_api.domains.structures.models import Structure, StructureIn
from mpcontribs_api.domains.structures.repository import MongoDbStructureRepository
from mpcontribs_api.domains.tables.models import Table, TableIn
from mpcontribs_api.domains.tables.repository import MongoDbTableRepository
from mpcontribs_api.exceptions import ValidationError


class ContributionService:
    def __init__(
        self,
        contributions: MongoDbContributionRepository,
        structures: MongoDbStructureRepository,
        attachments: MongoDbAttachmentRepository,
        tables: MongoDbTableRepository,
    ):
        self._contributions = contributions
        self._structures = structures
        self._attachments = attachments
        self._tables = tables

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

        structures = await self._structures.insert_structures(all_structures)
        tables = await self._tables.insert_tables(all_tables)
        attachments = await self._attachments.insert_attachments(all_attachments)

        return structures, tables, attachments, struct_slices, table_slices, attach_slices

    async def insert_contributions(self, contributions: list[ContributionIn]):
        """Bulk insertion of Contributions with nested components.

        Components embedded in each ContributionIn are bulk-inserted first; the resulting IDs
        are stored as Links before the contributions themselves are bulk-inserted.

        Args:
            contributions: contributions to insert, may include nested structures/tables/attachments

        Returns:
            list[Contribution]: inserted documents
        """
        structures, tables, attachments, struct_slices, table_slices, attach_slices = await self._insert_components(
            contributions
        )

        full_docs: list[Contribution] = []
        for i, contrib in enumerate(contributions):
            doc = Contribution.from_input_model(contrib)
            doc.structures = cast(list[Link[Structure]] | None, structures[struct_slices[i]] or None)
            doc.tables = cast(list[Link[Table]] | None, tables[table_slices[i]] or None)
            doc.attachments = cast(list[Link[Attachment]] | None, attachments[attach_slices[i]] or None)
            full_docs.append(doc)

        return await self._contributions.insert_many_contributions(full_docs)

    async def upsert_contributions(self, contributions: list[ContributionIn]):
        """Upsert contributions by (project, identifier).

        Components (structures, tables, attachments) must be managed via their respective
        services. If any contribution in the batch carries components, the entire request is
        rejected before any database writes occur.

        Args:
            contributions: contributions to upsert; must not include nested components

        Returns:
            list[Contribution]: upserted documents
        """
        indices_with_components = [i for i, c in enumerate(contributions) if c.structures or c.tables or c.attachments]
        if indices_with_components:
            raise ValidationError(
                "Components must be managed via their respective services, not via contribution upsert.",
                contribution_indices=indices_with_components,
            )

        async def _upsert(contrib: ContributionIn):
            doc = Contribution.from_input_model(contrib)
            existing = await self._contributions.find_one_contribution(contrib.project, contrib.identifier)
            if existing is not None:
                update_data = doc.model_dump(exclude={"id"}, exclude_none=True)
                await self._contributions.update_contribution(existing, update_data)
                return existing
            return await self._contributions.insert_contribution(doc)

        return await asyncio.gather(*[_upsert(c) for c in contributions])
