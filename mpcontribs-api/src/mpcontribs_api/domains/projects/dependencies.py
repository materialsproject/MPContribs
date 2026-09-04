from typing import Annotated

from fastapi import Depends

from mpcontribs_api.dependencies import UserDep
from mpcontribs_api.domains.consumers.dependencies import ConsumerServiceDep
from mpcontribs_api.domains.initiatives.repository import MongoDbInitiativeRepository
from mpcontribs_api.domains.projects.repository import (
    MongoDbProjectRepository,
)
from mpcontribs_api.domains.projects.service import ProjectService


async def get_project_service(user: UserDep, consumers: ConsumerServiceDep) -> ProjectService:
    return ProjectService(
        user=user,
        projects=MongoDbProjectRepository(user),
        initiatives=MongoDbInitiativeRepository(user),
        limits=await consumers.effective_limits(user.consumer_id),
    )


ProjectServiceDep = Annotated[ProjectService, Depends(get_project_service)]
