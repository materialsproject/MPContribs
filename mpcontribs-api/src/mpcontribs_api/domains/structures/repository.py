from typing import Any

from pymongo.asynchronous.client_session import AsyncClientSession

from mpcontribs_api.auth import User
from mpcontribs_api.config import get_settings
from mpcontribs_api.domains._shared.repository import MongoDbRepository
from mpcontribs_api.domains.structures.models import (
    Structure,
    StructureFilter,
    StructureIn,
    StructureOut,
    StructurePatch,
)


class MongoDbStructureRepository(
    MongoDbRepository[Structure, StructureIn, StructureOut, StructureFilter, StructurePatch]
):
    document_model = Structure
    out_model = StructureOut

    @staticmethod
    def _build_scope(user: User) -> dict[str, Any]:
        return {}

    async def insert_structures(
        self,
        structures: list[StructureIn],
        session: AsyncClientSession | None = None,
    ) -> list[Structure]:
        """Bulk-insert structures, chunked to fit within a transaction's payload budget.

        Args:
            structures: structures to insert
            session: optional client session; pass when inserting inside a transaction
        """
        if not structures:
            return []
        docs = [Structure.model_validate(s.model_dump()) for s in structures]
        chunk_size = get_settings().mongo.component_insert_chunk_size
        for start in range(0, len(docs), chunk_size):
            await Structure.insert_many(docs[start : start + chunk_size], ordered=False, session=session)
        return docs
