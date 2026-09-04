from fastapi import APIRouter

from mpcontribs_api.config import get_settings
from mpcontribs_api.dependencies import UserDep
from mpcontribs_api.domains.consumers.dependencies import ConsumerServiceDep
from mpcontribs_api.domains.limits.models import Limits

router = APIRouter()


@router.get("", response_model=Limits, summary="Server-enforced request limits")
async def get_limits(user: UserDep, consumers: ConsumerServiceDep) -> Limits:
    """Return the request limits the server enforces for the caller.

    The three infra limits are global (from ``mongo``); ``max_components`` is resolved per-consumer
    (an anonymous caller gets the global default). Public metadata; no auth required.
    """
    mongo = get_settings().mongo
    limits = await consumers.effective_limits(user.consumer_id)
    return Limits(
        max_request_bytes=mongo.max_request_bytes,
        bulk_write_limit=mongo.bulk_write_limit,
        max_components=limits.contribution.max_components,
        component_insert_chunk_size=mongo.component_insert_chunk_size,
    )
