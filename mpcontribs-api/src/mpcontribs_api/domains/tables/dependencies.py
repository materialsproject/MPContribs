from typing import Annotated

from fastapi import Depends

from mpcontribs_api.dependencies import UserDep
from mpcontribs_api.domains._shared.service import ComponentService
from mpcontribs_api.domains.contributions.repository import MongoDbContributionRepository
from mpcontribs_api.domains.tables.models import (
    Table,
    TableFilter,
    TableIn,
    TableOut,
    TablePatch,
)
from mpcontribs_api.domains.tables.repository import MongoDbTableRepository

TableService = ComponentService[Table, TableIn, TableOut, TableFilter, TablePatch]


def get_table_service(user: UserDep) -> TableService:
    return ComponentService(
        MongoDbTableRepository(user),
        MongoDbContributionRepository(user),
        ref_field="tables",
    )


TableServiceDep = Annotated[TableService, Depends(get_table_service)]
