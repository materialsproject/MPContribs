from typing import Annotated

from fastapi import Depends

from mpcontribs_api.dependencies import UserDep
from mpcontribs_api.domains.components.service import ComponentService
from mpcontribs_api.domains.contributions.repository import MongoDbContributionRepository
from mpcontribs_api.domains.structures.models import StructureFilter, StructureOut
from mpcontribs_api.domains.structures.repository import MongoDbStructureRepository

StructureService = ComponentService[StructureOut, StructureFilter]


def get_structure_service(user: UserDep) -> StructureService:
    return ComponentService(
        MongoDbStructureRepository(user),
        MongoDbContributionRepository(user),
        subtype="structure",
        ref_field="structures",
    )


StructureServiceDep = Annotated[StructureService, Depends(get_structure_service)]
