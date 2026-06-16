from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from mpcontribs_api.config import get_settings
from mpcontribs_api.dependencies import DbDep, S3Dep

router = APIRouter(tags=["health"])

settings = get_settings()


class HealthStatus(BaseModel):
    status: str
    mongo: str
    s3: str


@router.get("", response_model=HealthStatus, summary="Service health")
async def healthcheck(db: DbDep, s3_client: S3Dep) -> HealthStatus:
    try:
        await db.client.admin.command("ping")
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "unhealthy", "mongo": "unreachable"},
        ) from None

    try:
        await s3_client.head_bucket(Bucket=settings.aws.health_bucket)
    except (ClientError, BotoCoreError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "unhealthy", "s3": "unreachable"},
        ) from None

    return HealthStatus(status="healthy", mongo="ok", s3="ok")
