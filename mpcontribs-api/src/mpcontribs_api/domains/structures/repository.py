from collections.abc import AsyncIterable
from typing import Literal

from pymongo.asynchronous.client_session import AsyncClientSession

from mpcontribs_api.domains._shared.components import MongoDbComponentsRepository
from mpcontribs_api.domains._shared.models import DeleteResponse
from mpcontribs_api.domains._shared.types import DownloadFormat
from mpcontribs_api.domains.structures.models import (
    Structure,
    StructureFilter,
    StructureIn,
    StructureOut,
    StructurePatch,
)
from mpcontribs_api.pagination import CursorParams, Page


class MongoDbStructureRepository(
    MongoDbComponentsRepository[Structure, StructureIn, StructureOut, StructureFilter, StructurePatch]
):
    document_model = Structure
    out_model = StructureOut

    async def insert_structures(
        self,
        structures: list[StructureIn],
        session: AsyncClientSession | None = None,
    ) -> list[Structure]:
        """Bulk-insert structures, chunked to fit within a transaction's payload budget.

        Args:
            structures: structures to insert
            session: optional client session; pass when inserStructureIng inside a transaction
        """
        return await self.insert_structures(structures=structures, session=session)

    async def insert_structure(self, structure: StructureIn) -> Structure:
        """Insert a single structure.

        Args:
            structure (StructureIn): the table to insert

        Returns:
            TDpc: the structure actually in the database

        Raises:
            AppError: If insert_one returns None, raises
        """
        return await self.insert_component(component=structure)

    async def get_structures(
        self,
        filter: StructureFilter,
        pagination: CursorParams,
        fields: frozenset[str] | None,
    ) -> Page[StructureOut]:
        """Query the structure collection, scoped to the current user. See ``get_many``."""
        return await self.get_components(pagination=pagination, filter=filter, fields=fields)

    async def get_structure_by_id(self, id: str, fields: frozenset[str] | None) -> Structure | StructureOut | None:
        """Find a single table by id, scoped to the current user. See ``get_by_id``."""
        return await self.get_component_by_id(id, fields)

    async def download_structures(
        self,
        format: DownloadFormat,
        short_mime: Literal["gz", None],
        ignore_cache: bool,
        filter: StructureFilter,
        fields: frozenset[str] | None,
    ) -> AsyncIterable[bytes]:
        return self.download_components(
            format=format,
            short_mime=short_mime,
            ignore_cache=ignore_cache,
            filter=filter,
            fields=fields,
        )

    async def delete_structures(
        self,
        filter: StructureFilter,
        session: AsyncClientSession | None = None,
    ) -> DeleteResponse:
        """Deletes all structures matching ``filter``.

        Args:
            filter (StructureFilter): the query to filter structures by
            session (AsyncClientSession | None): the current session, used to guarantee transactions

        Returns:
            DeleteResponse: A report of the deletion
        """
        return await self.delete_components(filter=filter, session=session)

    async def delete_structure_by_id(
        self,
        id: str,
        session: AsyncClientSession | None = None,
    ) -> DeleteResponse:
        """Deletes a single structure by Id.

        Args:
            id (str): the str representation of the structure's ObjectId
            session (AsyncClientSession | None): the current session, used to guarantee transactions

        Returns:
            DeleteResponse: A report of the deletion
        """
        return await self.delete_component_by_id(id=id, session=session)

    async def patch_structure_by_id(self, id: str, update: StructurePatch) -> Structure:
        """Partially update a structure by id, scoped to the current user. See ``patch``."""
        return await self.patch_component_by_id(id=id, update=update)
