from typing import Any

from pymongo.asynchronous.client_session import AsyncClientSession

from mpcontribs_api.auth import User
from mpcontribs_api.config import get_settings
from mpcontribs_api.domains._shared.repository import MongoDbRepository
from mpcontribs_api.domains.tables.models import (
    Table,
    TableDocumentOut,
    TableFilter,
    TableIn,
    TablePatch,
)


class MongoDbTableRepository(MongoDbRepository[Table, TableIn, TableDocumentOut, TableFilter, TablePatch]):
    document_model = Table
    out_model = TableDocumentOut

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
        docs = [Table.model_validate(t.model_dump()) for t in tables]
        chunk_size = get_settings().mongo.component_insert_chunk_size
        for start in range(0, len(docs), chunk_size):
            await Table.insert_many(docs[start : start + chunk_size], ordered=False, session=session)
        return docs
