from datetime import UTC, datetime
from enum import StrEnum
from typing import ClassVar, Self

from beanie import PydanticObjectId
from pydantic import BaseModel, SerializeAsAny
from pymongo import ASCENDING, IndexModel

from mpcontribs_api.config import get_settings
from mpcontribs_api.domains._shared.filters import BaseFilter
from mpcontribs_api.domains._shared.models import BaseDocumentWithInput, DocumentOut, canonical_md5
from mpcontribs_api.domains._shared.types import DownloadFormat, Identity, ShortMimeFormat, download_filename
from mpcontribs_api.projection import SparseFieldsModel


class JobStatus(StrEnum):
    submitted = "submitted"
    ready = "ready"
    error = "error"


class DownloadIdentity(Identity):
    """Natural key of a download doc in MongoDB.

    `requester` is the `consumer_id` of the user that requested the download.
    `s3_key` is the stable hash of the file generated.

    Field order is the compound-index column order.
    """

    requester: str
    s3_key: str


class Download(BaseDocumentWithInput[PydanticObjectId]):
    identity_model: ClassVar[type[Identity]] = DownloadIdentity
    s3_key: str
    status: JobStatus
    requester: str
    query: dict
    domain: str
    fmt: DownloadFormat
    rows_written: int = 0
    bytes_written: int = 0
    error: str | None = None
    created_at: datetime

    class Settings:
        name = "downloads"
        keep_nulls = False
        indexes = [
            IndexModel(
                name="download_ttl_index",
                keys=[("created_at", ASCENDING)],
                expireAfterSeconds=get_settings().mpcontribs.downloads_cache_ttl,
            ),
            DownloadIdentity.index_model(name="requester_s3_key", unique=True),
        ]

    @staticmethod
    def build_s3_key(domain: str, fmt: DownloadFormat, query: dict) -> str:
        """Derive the deterministic S3 object key for a download request.

        The digest covers the domain, format, and query — everything that changes the bytes of the
        file. The query already carries the caller's access scope by the time it reaches here, so
        two callers only share a cached object when they would see the same rows. The requester is
        left off so a cached object is shareable across callers with the same scope.
        """
        digest = canonical_md5({"domain": domain, "fmt": fmt.value, "query": query})
        return download_filename(f"{domain}/{digest}", fmt, ShortMimeFormat.GZ)

    @classmethod
    def from_input_model(
        cls,
        data: DownloadIn,
    ) -> Self:
        created_at = datetime.now(UTC)
        query = data.filter.model_dump(mode="json", exclude_none=True)
        return cls.model_validate(
            obj={
                "_id": PydanticObjectId(),
                "s3_key": cls.build_s3_key(data.domain, data.fmt, query),
                "status": data.status,
                "requester": data.requester,
                "query": query,
                "domain": data.domain,
                "fmt": data.fmt,
                "created_at": created_at,
            }
        )


class DownloadIn(BaseModel):
    status: JobStatus
    requester: str
    filter: SerializeAsAny[BaseFilter]
    domain: str
    fmt: DownloadFormat


class DownloadOut(DocumentOut):
    s3_key: str | None = None
    status: JobStatus | None = None
    requester: str | None = None
    query: dict | None = None
    domain: str | None = None
    fmt: DownloadFormat | None = None
    rows_written: int = 0
    bytes_written: int = 0
    error: str | None = None
    created_at: datetime | None = None


class DownloadPatch(SparseFieldsModel):
    # ``s3_key`` is assigned deterministically at submit time and never patched; a worker updates
    # only the job's progress/outcome.
    status: JobStatus | None = None
    rows_written: int | None = None
    bytes_written: int | None = None
    error: str | None = None


class DownloadFilter(BaseFilter):
    status: JobStatus | None = None
    requester: str | None = None
    requester__in: list[str] | None = None
    fmt: DownloadFormat | None = None
    fmt__in: DownloadFormat | None = None
    error: str | None = None
    error__in: str | None = None
    error_neq: str | None = None
    s3_key: str | None = None
    s3_key__in: list[str] | None = None
    created_at: datetime | None = None
    created_at__lte: datetime | None = None
    created_at__gte: datetime | None = None
