from typing import Any

from pymongo.asynchronous.client_session import AsyncClientSession

from mpcontribs_api.auth import User
from mpcontribs_api.config import get_settings
from mpcontribs_api.domains._shared.repository import MongoDbRepository
from mpcontribs_api.domains._shared.types import DownloadFormat
from mpcontribs_api.domains.tables.models import (
    Table,
    TableFilter,
    TableIn,
    TableOut,
    TablePatch,
)
from mpcontribs_api.pagination import CursorParams, Page


class MongoDbTableRepository(MongoDbRepository[Table, TableIn, TableOut, TableFilter, TablePatch]):
    document_model = Table
    out_model = TableOut

    @staticmethod
    def _build_scope(user: User) -> dict[str, Any]:
        return {}

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

    async def get_tables(
        self,
        filter: TableFilter,
        pagination: CursorParams,
        fields: frozenset[str] | None,
    ) -> Page[TableOut]:
        """Query the Table collection, scoped to the current user. See ``get_many``."""
        return await self.get_many(pagination=pagination, filter=filter, fields=fields)

    async def get_table_by_id(self, id: str, fields: frozenset[str] | None):
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
