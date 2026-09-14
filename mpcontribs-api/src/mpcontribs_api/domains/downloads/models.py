import json
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from hashlib import md5
from typing import Self

from beanie import PydanticObjectId
from pydantic import BaseModel
from pymongo import ASCENDING, IndexModel

from mpcontribs_api.config import get_settings
from mpcontribs_api.domains._shared.models import BaseDocumentWithInput, DocumentOut
from mpcontribs_api.domains._shared.types import DownloadFormat, Identity


class JobStatus(StrEnum):
    submitted = "submitted"
    ready = "ready"
    error = "error"


class DownloadIdentity(Identity):
    cache_key: str


class Download(BaseDocumentWithInput[PydanticObjectId]):
    cache_key: str
    status: JobStatus
    requester: str
    scope_hash: str
    query: dict
    include: list[str]
    fmt: DownloadFormat
    rows_written: int = 0
    bytes_written: int = 0
    error: str | None = None
    s3_key: str | None = None
    created_at: datetime
    expires_at: datetime

    class Settings:
        name = "downloads"
        keep_nulls = False
        indexes = [
            DownloadIdentity.index_model(name="cache_key"),
            IndexModel(keys=[("s3_key", ASCENDING)], name="s3_key"),
        ]

    @classmethod
    def from_input_model(
        cls,
        data: DownloadIn,
    ) -> Self:
        settings = get_settings()
        created_at = datetime.now(UTC)
        return cls.model_validate(
            obj={
                **data.model_dump(),
                "cache_key": md5(json.dumps(data, sort_keys=True).encode("utf-8")),
                "created_at": created_at,
                "expires_at": created_at + timedelta(hours=settings.mpcontribs.downloads_cache_ttl),
            }
        )


class DownloadIn(BaseModel):
    status: JobStatus
    requester: str
    scope_hash: str
    query: dict
    include: list[str]
    fmt: DownloadFormat


class DownloadOut(DocumentOut):
    cache_key: str
    status: JobStatus
    requester: str
    scope_hash: str
    query: dict
    include: list[str]
    fmt: DownloadFormat
    rows_written: int = 0
    bytes_written: int = 0
    error: str | None = None
    s3_key: str | None = None
    created_at: datetime
    expires_at: datetime
