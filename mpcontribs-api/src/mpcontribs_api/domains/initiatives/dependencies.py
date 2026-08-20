from typing import Annotated

from fastapi import Depends

from mpcontribs_api.dependencies import UserDep
from mpcontribs_api.domains.initiatives.repository import MongoDbInitiativeRepository
from mpcontribs_api.domains.initiatives.service import InitiativeService
from mpcontribs_api.domains.projects.repository import MongoDbProjectRepository


def get_initiative_service(user: UserDep) -> InitiativeService:
    return InitiativeService(
        user=user,
        initiatives=MongoDbInitiativeRepository(user),
        projects=MongoDbProjectRepository(user),
    )


InitiativeServiceDep = Annotated[InitiativeService, Depends(get_initiative_service)]
