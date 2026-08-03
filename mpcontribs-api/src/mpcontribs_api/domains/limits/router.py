from fastapi import APIRouter

from mpcontribs_api.config import get_settings
from mpcontribs_api.domains.limits.models import Limits

router = APIRouter()


@router.get("", response_model=Limits, summary="Server-enforced request limits")
async def get_limits() -> Limits:
    """Return the request limits the server enforces. Public metadata; no auth required."""
    mongo = get_settings().mongo
    return Limits(
        max_request_bytes=mongo.max_request_bytes,
        bulk_write_limit=mongo.bulk_write_limit,
        max_components_per_contribution=mongo.max_components_per_contribution,
        component_insert_chunk_size=mongo.component_insert_chunk_size,
    )
