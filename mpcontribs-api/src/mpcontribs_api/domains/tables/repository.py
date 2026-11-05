from mpcontribs_api.domains.components.repository import MongoDbComponentsRepository
from mpcontribs_api.domains.tables.models import Table, TableFilter, TableOut


class MongoDbTableRepository(MongoDbComponentsRepository[Table, TableOut, TableFilter]):
    """Repository for the thin, content-addressed table index.

    All behavior (reads, cascade delete, empty read scope) comes from
    :class:`MongoDbComponentsRepository`; this subclass only binds the collection.
    """

    document_model = Table
    out_model = TableOut
