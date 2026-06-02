from typing import Annotated, Literal

from fastapi import APIRouter, Query
from fastapi_filter import FilterDepends

from src.mpcontribs_api.domains.contributions.dependencies import ContributionDep
from src.mpcontribs_api.domains.contributions.models import (
    ContributionFilter,
    ContributionIn,
    ContributionPatch,
)
from src.mpcontribs_api.pagination import CursorParams

router = APIRouter()


@router.get("")
async def get_contributions(
    repo: ContributionDep,
    pagination: Annotated[CursorParams, Query()],
    filter: ContributionFilter = FilterDepends(ContributionFilter),
    fields: Annotated[str | None, Query(alias="_fields")] = None,
):
    pass


@router.delete("")
async def delete_contributions(
    repo: ContributionDep,
    filter: ContributionFilter = FilterDepends(ContributionFilter),
):
    pass


@router.post("")
async def insert_contributions(
    repo: ContributionDep,
    contributions: list[ContributionIn],
):
    pass


@router.put("")
async def upsert_contributions(
    repo: ContributionDep,
    contributions: list[ContributionIn],
    filter: ContributionFilter = FilterDepends(ContributionFilter),
):
    pass


@router.get("download/{mime}")
async def download_contributions(
    repo: ContributionDep,
    format: Literal["json", "csv", "parquet"] = "parquet",
    filter: ContributionFilter = FilterDepends(ContributionFilter),
    fields: Annotated[str | None, Query(alias="_fields")] = None,
):
    pass


@router.delete("{id}")
async def delete_contribtion_by_id(
    repo: ContributionDep,
    id: str,
):
    pass


@router.get("{id}")
async def get_contribution_by_id(
    repo: ContributionDep,
    id: str,
    fields: Annotated[str | None, Query(alias="_fields")] = None,
):
    pass


@router.put("{id}")
async def upsert_contribution_by_id(
    repo: ContributionDep, id: str, contribution: ContributionIn
):
    pass


@router.patch("{id}")
async def update_contribution_by_id(
    repo: ContributionDep, id: str, update: ContributionPatch
):
    pass
