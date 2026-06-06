from typing import Any

from mpcontribs_api.auth import User
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

    async def insert_tables(self, tables: list[TableIn]) -> list[Table]:
        if not tables:
            return []
        docs = [Table.model_validate(t.model_dump()) for t in tables]
        await Table.insert_many(docs, ordered=False)
        return docs
