from typing import Annotated

from fastapi import Depends

from mpcontribs_api.dependencies import UserDep
from mpcontribs_api.domains._shared.service import ComponentService
from mpcontribs_api.domains.contributions.repository import MongoDbContributionRepository
from mpcontribs_api.domains.structures.models import (
    Structure,
    StructureFilter,
    StructureIn,
    StructureOut,
    StructurePatch,
)
from mpcontribs_api.domains.structures.repository import MongoDbStructureRepository

StructureService = ComponentService[Structure, StructureIn, StructureOut, StructureFilter, StructurePatch]


def get_structure_service(user: UserDep) -> StructureService:
    return ComponentService(
        MongoDbStructureRepository(user),
        MongoDbContributionRepository(user),
        ref_field="structures",
    )


StructureServiceDep = Annotated[StructureService, Depends(get_structure_service)]
