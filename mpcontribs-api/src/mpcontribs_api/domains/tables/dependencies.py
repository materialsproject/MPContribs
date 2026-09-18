from typing import Annotated

from fastapi import Depends

from mpcontribs_api.dependencies import S3Dep, SQSDep, UserDep
from mpcontribs_api.domains._shared.service import ComponentService
from mpcontribs_api.domains.contributions.repository import MongoDbContributionRepository
from mpcontribs_api.domains.downloads.service import DownloadService
from mpcontribs_api.domains.tables.models import (
    Table,
    TableFilter,
    TableIn,
    TableOut,
    TablePatch,
)
from mpcontribs_api.domains.tables.repository import MongoDbTableRepository

TableService = ComponentService[Table, TableIn, TableOut, TableFilter, TablePatch]


def get_table_service(user: UserDep, sqs: SQSDep, s3: S3Dep) -> TableService:
    return ComponentService(
        MongoDbTableRepository(user),
        MongoDbContributionRepository(user),
        user=user,
        downloads=DownloadService(user, sqs=sqs, s3=s3),
        ref_field="tables",
    )


TableServiceDep = Annotated[TableService, Depends(get_table_service)]
