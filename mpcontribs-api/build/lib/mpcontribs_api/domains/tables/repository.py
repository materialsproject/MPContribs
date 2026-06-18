from mpcontribs_api.domains._shared.components import MongoDbComponentsRepository
from mpcontribs_api.domains.tables.models import (
    Table,
    TableFilter,
    TableIn,
    TableOut,
    TablePatch,
)


class MongoDbTableRepository(MongoDbComponentsRepository[Table, TableIn, TableOut, TableFilter, TablePatch]):
    document_model = Table
    out_model = TableOut
