from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from fastapi_filter import FilterDepends

from mpcontribs_api.domains._shared.bulk import BulkWriteSummary
from mpcontribs_api.domains._shared.types import FieldSelector
from mpcontribs_api.domains.contributions.dependencies import ContributionDep, ContributionServiceDep
from mpcontribs_api.domains.contributions.models import (
    Contribution,
    ContributionFilter,
    ContributionIn,
    ContributionOut,
    ContributionPatch,
)
from mpcontribs_api.pagination import CursorParams

router = APIRouter(tags=["contributions"])


@router.get("")
async def get_contributions(
    repo: ContributionDep,
    pagination: Annotated[CursorParams, Depends()],
    filter: ContributionFilter = FilterDepends(ContributionFilter),
    fields: FieldSelector = ContributionOut.default_fields(),
):
    field_set = ContributionOut.parse_fields(fields)
    return await repo.get_contributions(pagination=pagination, filter=filter, fields=field_set)


@router.delete("")
async def delete_contributions(
    repo: ContributionDep,
    filter: ContributionFilter = FilterDepends(ContributionFilter),
):
    return await repo.delete_contributions(filter=filter)


# TODO: Might want to take contributions in from request body and run model_validate_json on it (much faster)
@router.post("", response_model=BulkWriteSummary[Contribution])
async def insert_contributions(
    service: ContributionServiceDep,
    contributions: list[ContributionIn],
):
    return await service.insert_contributions(contributions=contributions)


@router.put("")
async def upsert_contributions(
    service: ContributionServiceDep,
    contributions: list[ContributionIn],
):
    return await service.upsert_contributions(contributions=contributions)


@router.get("download/{mime}")
async def download_contributions(
    repo: ContributionDep,
    format: Literal["json", "csv", "parquet"] = "parquet",
    filter: ContributionFilter = FilterDepends(ContributionFilter),
    fields: FieldSelector = ContributionOut.default_fields(),
):
    selected = ContributionOut.parse_fields(fields)
    return await repo.download_contributions(format=format, filter=filter, fields=selected)


@router.delete("{id}")
async def delete_contribtion_by_id(
    service: ContributionServiceDep,
    id: str,
):
    return await service.delete_contributions(ContributionFilter.model_validate({"id": id}))


@router.get("{id}")
async def get_contribution_by_id(
    repo: ContributionDep,
    id: str,
    fields: FieldSelector = ContributionOut.default_fields(),
):
    selected = ContributionOut.parse_fields(fields)
    return await repo.get_contribution_by_id(id=id, fields=selected)


@router.put("{id}")
async def upsert_contribution_by_id(repo: ContributionDep, id: str, contribution: ContributionIn):
    return await repo.upsert_contribution_by_id(id=id, contribution=contribution)


@router.patch("{id}")
async def patch_contribution_by_id(repo: ContributionDep, id: str, update: ContributionPatch):
    return await repo.patch_contribution_by_id(id=id, update=update)
