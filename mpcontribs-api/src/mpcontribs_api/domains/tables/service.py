from mpcontribs_api.domains._shared.service import ComponentService
from mpcontribs_api.domains.tables.models import TableFilter
from mpcontribs_api.domains.tables.repository import MongoDbTableRepository


class TableService(ComponentService[MongoDbTableRepository, TableFilter]):
    """Defines which field on a Contribtution to look in for the references."""

    ref_field = "tables"
