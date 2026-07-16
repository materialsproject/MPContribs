from typing import Annotated

from fastapi import Depends

from mpcontribs_api.dependencies import UserDep
from mpcontribs_api.domains.project_groups.repository import ProjectGroupRepository
from mpcontribs_api.domains.project_groups.service import ProjectGroupService
from mpcontribs_api.domains.projects.repository import MongoDbProjectRepository


def get_project_group_repository(user: UserDep) -> ProjectGroupRepository:
    return ProjectGroupRepository(user)


ProjectGroupDep = Annotated[ProjectGroupRepository, Depends(get_project_group_repository)]


def get_project_group_service(user: UserDep) -> ProjectGroupService:
    return ProjectGroupService(
        groups=ProjectGroupRepository(user),
        projects=MongoDbProjectRepository(user),
    )


ProjectGroupServiceDep = Annotated[ProjectGroupService, Depends(get_project_group_service)]
