from typing import Annotated

from fastapi import Depends

from mpcontribs_api.dependencies import UserDep
from mpcontribs_api.domains.attachments.repository import MongoDbAttachmentRepository
from mpcontribs_api.domains.consumers.dependencies import ConsumerServiceDep
from mpcontribs_api.domains.contributions.repository import MongoDbContributionRepository
from mpcontribs_api.domains.downloads.dependencies import DownloadServiceDep
from mpcontribs_api.domains.initiatives.repository import MongoDbInitiativeRepository
from mpcontribs_api.domains.projects.repository import (
    MongoDbProjectRepository,
)
from mpcontribs_api.domains.projects.service import ProjectService
from mpcontribs_api.domains.structures.repository import MongoDbStructureRepository
from mpcontribs_api.domains.tables.repository import MongoDbTableRepository


async def get_project_service(
    user: UserDep, consumers: ConsumerServiceDep, downloads: DownloadServiceDep
) -> ProjectService:
    return ProjectService(
        user=user,
        projects=MongoDbProjectRepository(user),
        initiatives=MongoDbInitiativeRepository(user),
        contributions=MongoDbContributionRepository(user),
        structures=MongoDbStructureRepository(user),
        tables=MongoDbTableRepository(user),
        attachments=MongoDbAttachmentRepository(user),
        downloads=downloads,
        limits=await consumers.effective_limits(user.consumer_id),
    )


ProjectServiceDep = Annotated[ProjectService, Depends(get_project_service)]
