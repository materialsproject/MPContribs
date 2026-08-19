from typing import Annotated

from fastapi import Depends

from mpcontribs_api.dependencies import UserDep
from mpcontribs_api.domains.initiatives.repository import InitiativeRepository


def get_initiative_repository(user: UserDep) -> InitiativeRepository:
    return InitiativeRepository(user)


InitiativeDep = Annotated[InitiativeRepository, Depends(get_initiative_repository)]
