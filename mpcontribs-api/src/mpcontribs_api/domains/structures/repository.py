from mpcontribs_api.domains._shared.components import MongoDbComponentsRepository
from mpcontribs_api.domains.structures.models import (
    Structure,
    StructureFilter,
    StructureIn,
    StructureOut,
    StructurePatch,
)


class MongoDbStructureRepository(
    MongoDbComponentsRepository[Structure, StructureIn, StructureOut, StructureFilter, StructurePatch]
):
    document_model = Structure
    out_model = StructureOut
