from typing import Annotated

from fastapi import Depends

from mpcontribs_api.dependencies import MongoClientDep, S3Dep, SQSDep, UserDep
from mpcontribs_api.domains.attachments.repository import MongoDbAttachmentRepository
from mpcontribs_api.domains.consumers.dependencies import ConsumerServiceDep
from mpcontribs_api.domains.contributions.repository import (
    MongoDbContributionRepository,
)
from mpcontribs_api.domains.contributions.service import ContributionService
from mpcontribs_api.domains.downloads.dependencies import DownloadServiceDep
from mpcontribs_api.domains.downloads.service import DownloadService
from mpcontribs_api.domains.projects.repository import MongoDbProjectRepository
from mpcontribs_api.domains.structures.repository import MongoDbStructureRepository
from mpcontribs_api.domains.tables.repository import MongoDbTableRepository


async def get_contribution_service(
    user: UserDep,
    client: MongoClientDep,
    consumers: ConsumerServiceDep,
    downloads: DownloadServiceDep,
    sqs: SQSDep,
    s3: S3Dep,
) -> ContributionService:
    return ContributionService(
        client=client,
        user=user,
        projects=MongoDbProjectRepository(user),
        contributions=MongoDbContributionRepository(user),
        structures=MongoDbStructureRepository(user),
        attachments=MongoDbAttachmentRepository(user),
        tables=MongoDbTableRepository(user),
        downloads=DownloadService(user, sqs=sqs, s3=s3),
        limits=await consumers.effective_limits(user.consumer_id),
    )


ContributionServiceDep = Annotated[ContributionService, Depends(get_contribution_service)]
