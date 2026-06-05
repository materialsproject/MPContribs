from typing import Any

from mpcontribs_api.auth import User
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

    async def insert_structures(self, structures: list[StructureIn]) -> list[Structure]:
        if not structures:
            return []
        docs = [Structure.model_validate(s.model_dump()) for s in structures]
        await Structure.insert_many(docs, ordered=False)
        return docs
