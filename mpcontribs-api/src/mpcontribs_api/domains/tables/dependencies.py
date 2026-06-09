from typing import Annotated

from fastapi import Depends

from mpcontribs_api.dependencies import UserDep
from mpcontribs_api.domains.tables.repository import MongoDbTableRepository


def get_scoped_tables(user: UserDep) -> MongoDbTableRepository:
    return MongoDbTableRepository(user)


TableDep = Annotated[MongoDbTableRepository, Depends(get_scoped_tables)]
