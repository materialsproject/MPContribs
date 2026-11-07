from typing import Annotated

from fastapi import Depends

from mpcontribs_api.dependencies import UserDep
from mpcontribs_api.domains.projects.repository import (
    MongoDbProjectRepository,
)
from mpcontribs_api.domains.projects.service import ProjectService


async def get_project_service(user: UserDep) -> ProjectService:
    return ProjectService(projects=MongoDbProjectRepository(user))


ProjectServiceDep = Annotated[ProjectService, Depends(get_project_service)]
