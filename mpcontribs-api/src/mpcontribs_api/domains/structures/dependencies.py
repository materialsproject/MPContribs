from typing import Annotated

from fastapi import Depends

from mpcontribs_api.dependencies import UserDep
from mpcontribs_api.domains.contributions.repository import MongoDbContributionRepository
from mpcontribs_api.domains.structures.repository import MongoDbStructureRepository
from mpcontribs_api.domains.structures.service import StructureService


def get_scoped_tables(user: UserDep) -> MongoDbStructureRepository:
    return MongoDbStructureRepository(user)


StructureDep = Annotated[MongoDbStructureRepository, Depends(get_scoped_tables)]


def get_structure_service(user: UserDep) -> StructureService:
    return StructureService(MongoDbStructureRepository(user), MongoDbContributionRepository(user))


StructureServiceDep = Annotated[StructureService, Depends(get_structure_service)]
