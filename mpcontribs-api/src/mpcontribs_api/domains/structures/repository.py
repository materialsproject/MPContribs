from mpcontribs_api.domains.components.repository import MongoDbComponentsRepository
from mpcontribs_api.domains.structures.models import Structure, StructureFilter, StructureOut


class MongoDbStructureRepository(MongoDbComponentsRepository[Structure, StructureOut, StructureFilter]):
    """Repository for the thin, content-addressed structure index.

    All behavior (reads, cascade delete, empty read scope) comes from
    :class:`MongoDbComponentsRepository`; this subclass only binds the collection.
    """

    document_model = Structure
    out_model = StructureOut
