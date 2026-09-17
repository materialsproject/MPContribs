from mpcontribs_api.domains._shared.repository import MongoDbRepository
from mpcontribs_api.domains.downloads.models import (
    Download,
    DownloadFilter,
    DownloadIn,
    DownloadOut,
    DownloadPatch,
)
from mpcontribs_api.scope import Owned, Scope


class MongoDbDownloadRepository(MongoDbRepository[Download, DownloadIn, DownloadOut, DownloadFilter, DownloadPatch]):
    """Repository for download-job documents.

    A download job is scoped to the `requester`. However, the physical file can be reused by multiple requesters when
    the download record hashes to the same s3_key - this provides deduplication of S3 objects, while still maintaining
    user privacy.
    """

    document_model = Download
    out_model = DownloadOut
    read_scope = Scope(Owned(field="requester"))
