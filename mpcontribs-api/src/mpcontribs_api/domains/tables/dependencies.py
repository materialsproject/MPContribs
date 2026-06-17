from typing import Annotated

from fastapi import Depends

from mpcontribs_api.dependencies import UserDep
from mpcontribs_api.domains.contributions.repository import MongoDbContributionRepository
from mpcontribs_api.domains.tables.repository import MongoDbTableRepository
from mpcontribs_api.domains.tables.service import TableService


def get_scoped_tables(user: UserDep) -> MongoDbTableRepository:
    return MongoDbTableRepository(user)


TableDep = Annotated[MongoDbTableRepository, Depends(get_scoped_tables)]


def get_table_service(user: UserDep) -> TableService:
    return TableService(MongoDbTableRepository(user), MongoDbContributionRepository(user))


TableServiceDep = Annotated[TableService, Depends(get_table_service)]
