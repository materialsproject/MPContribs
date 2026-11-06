from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from fastapi_filter import FilterDepends

from mpcontribs_api.dependencies import S3Dep
from mpcontribs_api.domains._shared.types import (
    DownloadFormat,
    FieldSelector,
    ShortMimeFormat,
    download_filename,
)
from mpcontribs_api.domains.contributions.dependencies import ContributionServiceDep
from mpcontribs_api.domains.contributions.models import (
    ContributionFilter,
    ContributionIdentity,
    ContributionOut,
)
from mpcontribs_api.pagination import CursorParams, Page

# Contributions are worker-written documents: these endpoints are read-only. Creation, replacement,
# and deletion all flow through the /uploads endpoints.
router = APIRouter()


@router.get("", response_model_exclude_unset=True)
async def read_many(
    service: ContributionServiceDep,
    pagination: Annotated[CursorParams, Depends()],
    filter: ContributionFilter = FilterDepends(ContributionFilter),
    fields: FieldSelector = None,
) -> Page[ContributionOut]:
    selected = ContributionOut.parse_fields(fields)
    return await service.read_many(pagination=pagination, filter=filter, fields=selected)


@router.get("/download/{short_mime}")
async def download_contributions(
    service: ContributionServiceDep,
    s3: S3Dep,
    short_mime: ShortMimeFormat = ShortMimeFormat.GZ,
    format: DownloadFormat = DownloadFormat.JSONL,
    ignore_cache: bool = False,
    filter: ContributionFilter = FilterDepends(ContributionFilter),
    fields: FieldSelector = None,
) -> StreamingResponse:
    selected = ContributionOut.parse_fields(fields)
    body = await service.download(
        format=format,
        short_mime=short_mime,
        ignore_cache=ignore_cache,
        filter=filter,
        fields=selected,
        s3=s3,
    )
    filename = download_filename("contributions", format, short_mime)
    return StreamingResponse(
        body,
        media_type="application/gzip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# Declared before the ``/{id}`` routes so the literal ``item`` is never captured as an id.
@router.get("/item", response_model_exclude_unset=True)
async def read_one_by_identity(
    service: ContributionServiceDep,
    identity: Annotated[ContributionIdentity, Depends()],
    fields: FieldSelector = None,
) -> ContributionOut | None:
    """Return the contribution addressed by its natural identity, or None when none matches (409 if ambiguous)."""
    selected = ContributionOut.parse_fields(fields)
    return await service.read_one(identity.as_dict(), fields=selected)


@router.get("/search", response_model_exclude_unset=True)
async def search(
    service: ContributionServiceDep,
    query: str,
    limit: int = 10,
) -> list[ContributionOut]:
    """Search formulas.

    Declared before ``/{id}`` so the literal ``search`` segment is never captured as a contribution id.

    Args:
        service (ContributionServiceDep): the contribution service we depend on
        query (str): the free-text search string
        limit (int): the maximum number of matches to return

    Returns:
        list[ContributionOut]: the matching contributions
    """
    return await service.search(query, limit=limit)


@router.get("/{id}", response_model_exclude_unset=True)
async def read_one(
    service: ContributionServiceDep,
    id: str,
    fields: FieldSelector = None,
) -> ContributionOut | None:
    selected = ContributionOut.parse_fields(fields)
    return await service.read_one({"id": id}, fields=selected)
