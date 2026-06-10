from typing import Any

from pymongo.asynchronous.client_session import AsyncClientSession

from mpcontribs_api.auth import User
from mpcontribs_api.config import get_settings
from mpcontribs_api.domains._shared.models import DeleteResponse
from mpcontribs_api.domains._shared.repository import MongoDbRepository
from mpcontribs_api.domains._shared.types import DownloadFormat
from mpcontribs_api.domains.tables.models import (
    Table,
    TableFilter,
    TableIn,
    TableOut,
    TablePatch,
)
from mpcontribs_api.exceptions import AppError
from mpcontribs_api.pagination import CursorParams, Page


class MongoDbTableRepository(MongoDbRepository[Table, TableIn, TableOut, TableFilter, TablePatch]):
    document_model = Table
    out_model = TableOut

    @staticmethod
    def _build_scope(user: User) -> dict[str, Any]:
        return {}

    # TODO: Returned docs don't have IDs assigned to them
    async def insert_tables(
        self,
        tables: list[TableIn],
        session: AsyncClientSession | None = None,
    ) -> list[Table]:
        """Bulk-insert tables, chunked to fit within a transaction's payload budget.

        Args:
            tables: tables to insert
            session: optional client session; pass when inserting inside a transaction
        """
        if not tables:
            return []
        docs = [self.document_model.model_validate(t.model_dump()) for t in tables]
        chunk_size = get_settings().mongo.component_insert_chunk_size
        for start in range(0, len(docs), chunk_size):
            await self.document_model.insert_many(docs[start : start + chunk_size], ordered=False, session=session)
        return docs

    async def insert_table(self, table: TableIn) -> Table:
        """Insert a single table.

        Args:
            table (TableIn): the table to insert

        Returns:
            Table: the table actually in the database

        Raises:
            AppError: If insert_one returns None, raises
        """
        doc = self.document_model.model_validate(table.model_dump())
        full_doc = await self.document_model.insert_one(doc)
        if not full_doc:
            raise AppError("Error inserting Table", table=table)
        return full_doc

    async def get_tables(
        self,
        filter: TableFilter,
        pagination: CursorParams,
        fields: frozenset[str] | None,
    ) -> Page[TableOut]:
        """Query the Table collection, scoped to the current user. See ``get_many``."""
        return await self.get_many(pagination=pagination, filter=filter, fields=fields)

    async def get_table_by_id(self, id: str, fields: frozenset[str] | None) -> Table | TableOut | None:
        """Find a single table by id, scoped to the current user. See ``get_by_id``."""
        return await self.get_by_id(id, fields)

    async def download_tables(
        self,
        format: DownloadFormat,
        short_mime: str,
        filter: TableFilter,
        fields: frozenset[str] | None,
    ):
        pass

    async def delete_tables(
        self,
        filter: TableFilter,
        session: AsyncClientSession | None = None,
    ) -> DeleteResponse:
        """Deletes all tables matching ``filter``.

        Args:
            filter (TableFilter): the query to filter tables by
            session (AsyncClientSession | None): the current session, used to guarantee transactions

        Returns:
            DeleteResponse: A report of the deletion
        """
        query = filter.filter(self.document_model.find(self._scope, session=session))
        result = await query.delete(session=session)
        return DeleteResponse(num_deleted=result.deleted_count if result else 0)

    async def delete_table_by_id(
        self,
        id: str,
        session: AsyncClientSession | None = None,
    ) -> DeleteResponse:
        """Deletes a single table by Id.

        Args:
            id (str): the str representation of the Table's ObjectId
            session (AsyncClientSession | None): the current session, used to guarantee transactions

        Returns:
            DeleteResponse: A report of the deletion
        """
        return await self.delete_by_id(id=id, session=session)

    async def patch_table_by_id(self, id: str, update: TablePatch) -> Table:
        """Partially update a Table by id, scoped to the current user. See ``patch``."""
        return await self.patch(self._convert_object_id(id), update)
