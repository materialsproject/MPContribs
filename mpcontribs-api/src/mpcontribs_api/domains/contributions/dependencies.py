from typing import Annotated

from fastapi import Depends

from mpcontribs_api.dependencies import UserDep
from mpcontribs_api.domains.contributions.repository import (
    MongoDbContributionRepository,
)


def get_scoped_contributions(user: UserDep) -> MongoDbContributionRepository:
    return MongoDbContributionRepository(user)


ContributionDep = Annotated[
    MongoDbContributionRepository, Depends(get_scoped_contributions)
]
