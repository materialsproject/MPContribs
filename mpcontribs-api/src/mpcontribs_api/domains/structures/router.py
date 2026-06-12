from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response
from fastapi.responses import StreamingResponse
from fastapi_filter import FilterDepends

from mpcontribs_api.domains._shared.bulk import BulkWriteSummary
from mpcontribs_api.domains._shared.models import DeleteResponse
from mpcontribs_api.domains._shared.types import DownloadFormat, FieldSelector
from mpcontribs_api.domains.structures.dependencies import StructureDep
from mpcontribs_api.domains.structures.models import StructureFilter, StructureIn, StructureOut, StructurePatch
from mpcontribs_api.pagination import CursorParams, Page

router = APIRouter()


@router.get("", response_model=Page[StructureOut])
async def get_structures(
    repo: StructureDep,
    pagination: Annotated[CursorParams, Depends()],
    filter: StructureFilter = FilterDepends(StructureFilter),
    fields: FieldSelector = StructureOut.default_fields(),
):
    selected = StructureOut.parse_fields(fields)
    return await repo.get_structures(filter=filter, fields=selected, pagination=pagination)


@router.get("/{pk}", response_model=StructureOut)
async def get_structure(
    repo: StructureDep,
    pk: str,
    fields: FieldSelector = StructureOut.default_fields(),
):
    selected = StructureOut.parse_fields(fields)
    return await repo.get_structure_by_id(id=pk, fields=selected)


@router.get("/download/{short_mime}")
async def download_structure(
    repo: StructureDep,
    response: Response,
    format: DownloadFormat,
    short_mime: Literal["gz", None] = "gz",
    ignore_cache: bool = False,
    filter: StructureFilter = FilterDepends(StructureFilter),
    fields: FieldSelector = StructureOut.default_fields(),
) -> StreamingResponse:
    selected = StructureOut.parse_fields(fields)
    body = await repo.download_structures(
        format=format,
        short_mime=short_mime,
        ignore_cache=ignore_cache,
        filter=filter,
        fields=selected,
    )
    return StreamingResponse(
        body,
        media_type="application/gzip",
        headers={"Content-Disposition": 'attachment; filename="structures.jsonl.gz"'},
    )


@router.post("", response_model=BulkWriteSummary[StructureOut])
async def insert_structures(
    repo: StructureDep,
    structures: list[StructureIn],
):
    return await repo.insert_structures(structures=structures)


@router.delete("", response_model=DeleteResponse)
async def delete_structures(repo: StructureDep, filter: StructureFilter = FilterDepends(StructureFilter)):
    return await repo.delete_structures(filter=filter)


@router.delete("/{id}", response_model=DeleteResponse)
async def delete_structure_by_id(repo: StructureDep, id: str):
    return await repo.delete_structure_by_id(id=id)


@router.patch("/{id}")
async def patch_structure_by_id(
    repo: StructureDep,
    id: str,
    update: StructurePatch,
):
    return await repo.patch_structure_by_id(id=id, update=update)
