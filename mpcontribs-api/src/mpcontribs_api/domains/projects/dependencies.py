from typing import Annotated

from fastapi import Depends

from mpcontribs_api.dependencies import UserDep
from mpcontribs_api.domains.initiatives.repository import InitiativeRepository
from mpcontribs_api.domains.projects.repository import (
    MongoDbProjectRepository,
)
from mpcontribs_api.domains.projects.service import ProjectService


def get_scoped_projects(user: UserDep) -> MongoDbProjectRepository:
    return MongoDbProjectRepository(user)


ProjectDep = Annotated[MongoDbProjectRepository, Depends(get_scoped_projects)]


def get_project_service(user: UserDep) -> ProjectService:
    return ProjectService(
        projects=MongoDbProjectRepository(user),
        initiatives=InitiativeRepository(user),
    )


ProjectServiceDep = Annotated[ProjectService, Depends(get_project_service)]
