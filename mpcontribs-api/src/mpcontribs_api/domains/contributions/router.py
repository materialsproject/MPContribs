from typing import Annotated

from fastapi import APIRouter, Query
from fastapi_filter import FilterDepends

from src.mpcontribs_api.domains.contributions.dependencies import ContributionDep
from src.mpcontribs_api.domains.contributions.models import ContributionFilter
from src.mpcontribs_api.pagination import CursorParams

router = APIRouter()


@router.get("")
async def get_contribution(
    repo: ContributionDep,
    pagination: Annotated[CursorParams, Query()],
    filter: ContributionFilter = FilterDepends(ContributionFilter),
    fields: Annotated[str | None, Query(alias="_fields")] = None,
):
    pass
