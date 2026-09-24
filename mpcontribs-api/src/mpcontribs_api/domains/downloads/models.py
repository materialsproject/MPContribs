from datetime import UTC, datetime
from enum import StrEnum
from typing import ClassVar, Self

from beanie import PydanticObjectId
from pydantic import BaseModel
from pymongo import ASCENDING, IndexModel

from mpcontribs_api.config import get_settings
from mpcontribs_api.domains._shared.filters import BaseFilter
from mpcontribs_api.domains._shared.models import BaseDocumentWithInput, DocumentOut, canonical_sha256
from mpcontribs_api.domains._shared.types import DownloadFormat, Identity, ShortMimeFormat, download_filename
from mpcontribs_api.projection import SparseFieldsModel


class JobStatus(StrEnum):
    submitted = "submitted"
    ready = "ready"
    error = "error"


class DownloadDomain(StrEnum):
    """The downloadable collections.

    Used as the vocabulary for the keys of a download ``query`` map (a download can bundle a base
    collection plus related ones), not stored as a field on the ``Download`` doc.
    """

    projects = "projects"
    contributions = "contributions"
    structures = "structures"
    tables = "tables"
    attachments = "attachments"


class DownloadIdentity(Identity):
    """Natural key of a download doc in MongoDB.

    `requester` is the `username` of the (authenticated) user that requested the downloads
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
    # Map of ``{collection_name: [mongo_query, ...]}`` the worker runs to assemble the download.
    query: dict
    fmt: DownloadFormat
    rows_written: int = 0
    bytes_written: int = 0
    error: str | None = None
    # gets reset when retrying failed/hung downloads
    created_at: datetime
    # tracks original posting time so we can observe long-running tasks
    original_time: datetime

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

    # Lives in API server instead of worker so we can check for cache hits
    @staticmethod
    def build_s3_key(fmt: DownloadFormat, query: dict) -> str:
        """Derive the deterministic S3 object key for a download request.

        Includes the query, whose per-collection predicates embed the user's scope. This guarantees
        that a cache hit only occurs when users share the same scope, and thus do not risk leaking
        documents to each other. Stored flat: the collections being downloaded are encoded in the
        ``query`` keys, so no per-domain path prefix is needed.
        """
        digest = canonical_sha256({"fmt": fmt.value, "query": query})
        return download_filename(digest, fmt, ShortMimeFormat.GZ)

    @classmethod
    def from_input_model(
        cls,
        data: DownloadIn,
    ) -> Self:
        created_at = datetime.now(UTC)
        return cls.model_validate(
            obj={
                "_id": PydanticObjectId(),
                "s3_key": cls.build_s3_key(data.fmt, data.query),
                "status": data.status,
                "requester": data.requester,
                "query": data.query,
                "fmt": data.fmt,
                "created_at": created_at,
                "original_time": created_at,
            }
        )


class DownloadIn(BaseModel):
    status: JobStatus
    requester: str
    # Map of ``{collection_name: [mongo_query, ...]}`` the worker runs to build the download. Each
    # predicate already embeds the user's scope for that collection (see ``Download.query``).
    query: dict
    fmt: DownloadFormat


class DownloadOut(DocumentOut):
    s3_key: str | None = None
    status: JobStatus | None = None
    requester: str | None = None
    query: dict | None = None
    fmt: DownloadFormat | None = None
    rows_written: int = 0
    bytes_written: int = 0
    error: str | None = None
    created_at: datetime | None = None
    original_time: datetime | None = None


class DownloadPatch(SparseFieldsModel):
    # ``s3_key`` is assigned deterministically at submit time and never patched; a worker updates
    # only the job's progress/outcome.
    status: JobStatus | None = None
    rows_written: int | None = None
    bytes_written: int | None = None
    error: str | None = None


class DownloadFilter(BaseFilter):
    # Supplies the base repository's required ``TFilter`` type parameter. There is no download list endpoint.
    status: JobStatus | None = None
    requester: str | None = None
    requester__in: list[str] | None = None
    fmt: DownloadFormat | None = None
    fmt__in: list[DownloadFormat] | None = None
    error: str | None = None
    error__in: list[str] | None = None
    error_neq: str | None = None
    s3_key: str | None = None
    s3_key__in: list[str] | None = None
    created_at: datetime | None = None
    created_at__lte: datetime | None = None
    created_at__gte: datetime | None = None
    original_time: datetime | None = None
    original_time__lte: datetime | None = None
    original_time__gte: datetime | None = None
