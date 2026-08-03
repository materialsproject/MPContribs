from typing import Annotated

from fastapi import Depends

from mpcontribs_api.dependencies import UserDep
from mpcontribs_api.domains.consumers.dependencies import ConsumerLimitsDep
from mpcontribs_api.domains.projects.repository import (
    MongoDbProjectRepository,
)


def get_scoped_projects(user: UserDep, limits: ConsumerLimitsDep) -> MongoDbProjectRepository:
    return MongoDbProjectRepository(user, limits)


ProjectDep = Annotated[MongoDbProjectRepository, Depends(get_scoped_projects)]
