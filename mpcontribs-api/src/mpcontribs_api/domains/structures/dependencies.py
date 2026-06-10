from typing import Annotated

from fastapi import Depends

from mpcontribs_api.dependencies import UserDep
from mpcontribs_api.domains.structures.repository import MongoDbStructureRepository


def get_scoped_tables(user: UserDep) -> MongoDbStructureRepository:
    return MongoDbStructureRepository(user)


StructureDep = Annotated[MongoDbStructureRepository, Depends(get_scoped_tables)]
