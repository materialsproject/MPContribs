from typing import Annotated

from fastapi import Depends

from mpcontribs_api.dependencies import UserDep
from mpcontribs_api.domains.components.service import ComponentService
from mpcontribs_api.domains.contributions.repository import MongoDbContributionRepository
from mpcontribs_api.domains.tables.models import TableFilter, TableOut
from mpcontribs_api.domains.tables.repository import MongoDbTableRepository

TableService = ComponentService[TableOut, TableFilter]


def get_table_service(user: UserDep) -> TableService:
    return ComponentService(
        MongoDbTableRepository(user),
        MongoDbContributionRepository(user),
        subtype="table",
        ref_field="tables",
    )


TableServiceDep = Annotated[TableService, Depends(get_table_service)]
