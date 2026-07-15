from typing import Annotated

from fastapi import Depends

from mpcontribs_api.dependencies import MongoClientDep, UserDep
from mpcontribs_api.domains.attachments.repository import MongoDbAttachmentRepository
from mpcontribs_api.domains.contributions.repository import (
    MongoDbContributionRepository,
)
from mpcontribs_api.domains.contributions.service import ContributionService
from mpcontribs_api.domains.projects.repository import MongoDbProjectRepository
from mpcontribs_api.domains.structures.repository import MongoDbStructureRepository
from mpcontribs_api.domains.tables.repository import MongoDbTableRepository


def get_scoped_contributions(user: UserDep) -> MongoDbContributionRepository:
    return MongoDbContributionRepository(user)


ContributionDep = Annotated[MongoDbContributionRepository, Depends(get_scoped_contributions)]


def get_contribution_service(user: UserDep, client: MongoClientDep) -> ContributionService:
    return ContributionService(
        client=client,
        user=user,
        projects=MongoDbProjectRepository(user),
        contributions=MongoDbContributionRepository(user),
        structures=MongoDbStructureRepository(user),
        attachments=MongoDbAttachmentRepository(user),
        tables=MongoDbTableRepository(user),
    )


ContributionServiceDep = Annotated[ContributionService, Depends(get_contribution_service)]
