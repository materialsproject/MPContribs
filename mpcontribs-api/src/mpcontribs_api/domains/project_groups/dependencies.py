from typing import Annotated

from fastapi import Depends

from mpcontribs_api.dependencies import UserDep
from mpcontribs_api.domains.project_groups.repository import ProjectGroupRepository


def get_project_group_repository(user: UserDep) -> ProjectGroupRepository:
    return ProjectGroupRepository(user)


ProjectGroupDep = Annotated[ProjectGroupRepository, Depends(get_project_group_repository)]
