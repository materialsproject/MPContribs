from typing import Annotated

from fastapi import Depends

from mpcontribs_api.dependencies import UserDep
from mpcontribs_api.domains.initiatives.repository import InitiativeRepository
from mpcontribs_api.domains.initiatives.service import InitiativeService


def get_initiative_service(user: UserDep) -> InitiativeService:
    return InitiativeService(initiatives=InitiativeRepository(user))


InitiativeServiceDep = Annotated[InitiativeService, Depends(get_initiative_service)]
