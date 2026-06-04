from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from mpcontribs_api.dependencies import DbDep

router = APIRouter(tags=["health"])


class HealthStatus(BaseModel):
    status: str
    mongo: str


@router.get("", response_model=HealthStatus, summary="Service health")
async def healthcheck(db: DbDep) -> HealthStatus:
    try:
        await db.client.admin.command("ping")
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "unhealthy", "mongo": "unreachable"},
        ) from None
    return HealthStatus(status="healthy", mongo="ok")
