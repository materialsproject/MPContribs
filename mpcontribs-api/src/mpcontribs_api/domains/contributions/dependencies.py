from typing import Annotated

from fastapi import Depends

from mpcontribs_api.dependencies import UserDep
from mpcontribs_api.domains.contributions.repository import MongoDbContributionRepository
from mpcontribs_api.domains.contributions.service import ContributionService


async def get_contribution_service(user: UserDep) -> ContributionService:
    return ContributionService(contributions=MongoDbContributionRepository(user))


ContributionServiceDep = Annotated[ContributionService, Depends(get_contribution_service)]
