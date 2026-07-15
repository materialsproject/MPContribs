from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from fastapi_filter import FilterDepends

from mpcontribs_api.config import get_settings
from mpcontribs_api.dependencies import S3Dep, require_user
from mpcontribs_api.domains._shared.bulk import BulkWriteSummary
from mpcontribs_api.domains._shared.types import (
    DownloadFormat,
    FieldSelector,
    ShortMimeFormat,
    download_filename,
)
from mpcontribs_api.domains.contributions.dependencies import ContributionDep, ContributionServiceDep
from mpcontribs_api.domains.contributions.models import (
    Contribution,
    ContributionFilter,
    ContributionIn,
    ContributionOut,
    ContributionPatch,
)
from mpcontribs_api.exceptions import ValidationError
from mpcontribs_api.pagination import CursorParams

router = APIRouter()


def _enforce_bulk_limit(contributions: list[ContributionIn]) -> None:
    """Reject a bulk write larger than the configured per-request ceiling.

    Guards the synchronous bulk endpoints so a single request can't hand the service an unbounded
    list. Callers over the limit should chunk (the limit is advertised at ``GET /api/v1/limits``)
    or use the async bulk ingestion endpoint. Complements the body-size middleware, which bounds
    bytes rather than item count.
    """
    limit = get_settings().mongo.bulk_write_limit
    count = len(contributions)
    if count > limit:
        raise ValidationError(
            f"Bulk request of {count} contributions exceeds the per-request limit of {limit}. "
            "Chunk the request (see GET /api/v1/limits) or use the async bulk ingestion endpoint.",
            count=count,
            limit=limit,
        )


@router.get("")
async def get_contributions(
    repo: ContributionDep,
    pagination: Annotated[CursorParams, Depends()],
    filter: ContributionFilter = FilterDepends(ContributionFilter),
    fields: FieldSelector = ContributionOut.default_fields(),
):
    selected = ContributionOut.parse_fields(fields)
    return await repo.get_contributions(pagination=pagination, filter=filter, fields=selected)


@router.delete("", dependencies=[Depends(require_user)])
async def delete_contributions(
    repo: ContributionDep,
    filter: ContributionFilter = FilterDepends(ContributionFilter),
):
    return await repo.delete_contributions(filter=filter)


# TODO: Might want to take contributions in from request body and run model_validate_json on it (much faster)
@router.post("", response_model=BulkWriteSummary[Contribution], dependencies=[Depends(require_user)])
async def insert_contributions(
    service: ContributionServiceDep,
    contributions: list[ContributionIn],
):
    _enforce_bulk_limit(contributions)
    return await service.insert_contributions(contributions=contributions)


@router.put("", response_model=BulkWriteSummary[Contribution], dependencies=[Depends(require_user)])
async def upsert_contributions(
    service: ContributionServiceDep,
    contributions: list[ContributionIn],
):
    _enforce_bulk_limit(contributions)
    return await service.upsert_contributions(contributions=contributions)


@router.get("/download/{short_mime}")
async def download_contributions(
    repo: ContributionDep,
    s3: S3Dep,
    short_mime: ShortMimeFormat = ShortMimeFormat.GZ,
    format: DownloadFormat = DownloadFormat.JSONL,
    ignore_cache: bool = False,
    filter: ContributionFilter = FilterDepends(ContributionFilter),
    fields: FieldSelector = ContributionOut.default_fields(),
):
    selected = ContributionOut.parse_fields(fields)
    body = await repo.download_contributions(
        format=format,
        short_mime=short_mime,
        ignore_cache=ignore_cache,
        filter=filter,
        fields=selected,
        s3=s3,
        key_name="",  # TODO: Temp
    )
    filename = download_filename("contributions", format, short_mime)
    return StreamingResponse(
        body,
        media_type="application/gzip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/{id}", dependencies=[Depends(require_user)])
async def delete_contribution_by_id(
    service: ContributionServiceDep,
    id: str,
):
    return await service.delete_contributions(ContributionFilter.model_validate({"id": id}))


@router.get("/{id}")
async def get_contribution_by_id(
    repo: ContributionDep,
    id: str,
    fields: FieldSelector = ContributionOut.default_fields(),
):
    selected = ContributionOut.parse_fields(fields)
    return await repo.get_contribution_by_id(id=id, fields=selected)


@router.put("/{id}", dependencies=[Depends(require_user)])
async def upsert_contribution_by_id(repo: ContributionDep, id: str, contribution: ContributionIn):
    return await repo.upsert_contribution_by_id(id=id, contribution=contribution)


@router.patch("/{id}", dependencies=[Depends(require_user)])
async def patch_contribution_by_id(repo: ContributionDep, id: str, update: ContributionPatch):
    return await repo.patch_contribution_by_id(id=id, update=update)
