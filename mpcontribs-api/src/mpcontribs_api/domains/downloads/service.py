from datetime import UTC, datetime, timedelta

import structlog
from beanie import PydanticObjectId
from botocore.exceptions import BotoCoreError, ClientError
from pymongo.asynchronous.client_session import AsyncClientSession
from types_aiobotocore_s3 import S3Client
from types_aiobotocore_sqs.client import SQSClient

from mpcontribs_api.authz import User
from mpcontribs_api.config import get_settings
from mpcontribs_api.domains._shared.types import DownloadFormat
from mpcontribs_api.domains.downloads.models import (
    Download,
    DownloadDomain,
    DownloadIn,
    DownloadOut,
    DownloadPatch,
    JobStatus,
)
from mpcontribs_api.domains.downloads.repository import MongoDbDownloadRepository
from mpcontribs_api.exceptions import (
    DownloadRetryExhaustedError,
    JobStatusError,
    NotFoundError,
    PermissionError,
    S3Error,
    SqsError,
)

logger = structlog.get_logger(__name__)


def _as_utc(dt: datetime) -> datetime:
    """Treat a stored (naive-UTC, per the non-tz-aware Mongo client) datetime as tz-aware UTC."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


class DownloadService:
    """Owns the lifecycle of an async download job.

    A job is recorded as a :class:`Download` document (so its progress can be polled) and then
    handed to a background worker via a queue. This service only persists the job and enqueues it;
    the worker that streams the results to S3 and marks the job ``ready`` lives elsewhere.
    """

    def __init__(self, user: User, sqs: SQSClient, s3: S3Client) -> None:
        self._user = user
        self._downloads = MongoDbDownloadRepository(user)
        self._sqs = sqs
        self._s3 = s3

    async def read_one(
        self,
        download_id: PydanticObjectId,
        fields: frozenset[str] | None = None,
        session: AsyncClientSession | None = None,
    ) -> DownloadOut | None:
        """Return the caller's download by id, or ``None`` if it isn't theirs.

        The repository read scope restricts results to the requesting user's own downloads
        (``requester == username``), so another user's id resolves to ``None``.
        """
        return await self._downloads.read_one({"id": download_id}, fields=fields, session=session)

    async def queue_download(self, query: dict, domain: DownloadDomain, fmt: DownloadFormat) -> DownloadOut:
        """Assemble and enqueue a download job for the current user."""
        if self._user.username is None:
            raise PermissionError(required_role="authenticated")
        download_in = DownloadIn(
            status=JobStatus.submitted,
            requester=self._user.username,
            query=query,
            domain=domain,
            fmt=fmt,
        )
        return await self._submit(download_in)

    async def _submit(self, download_in: DownloadIn) -> DownloadOut:
        """Insert a Download document and add the download job to the queue if it needs running.

        A job is (re-)enqueued when it is:

        - newly created (first submission), or
        - ``error`` or
        - ``submitted`` but stale (older than ``downloads_stale_after``).

        A newly submitted job and a ready job are returned. A reclaimable job whose original_time is older
        than downloads_max_retry_age is refused, so perpetually failing requests stop being re-enqueued.
        """
        job = Download.from_input_model(download_in)
        stored, created = await self._downloads.insert_or_get(job)
        if created:
            await self._enqueue(stored)
            return DownloadOut.model_validate(stored.model_dump())
        if stored.status == JobStatus.ready:
            return DownloadOut.model_validate(stored.model_dump())  # cache hit

        now = datetime.now(UTC)
        settings = get_settings().mpcontribs
        # Mongo returns naive UTC datetimes; make them aware so they can be compared against the tz-aware ``now``.
        created_at = _as_utc(stored.created_at)
        original_time = _as_utc(stored.original_time)
        is_error = stored.status == JobStatus.error
        is_stale = stored.status == JobStatus.submitted and (
            now - created_at > timedelta(seconds=settings.downloads_stale_after)
        )
        if is_error or is_stale:
            # Abuse/robustness guard: refuse to keep retrying a ticket that has been failing since
            # longer ago than the cap.
            if now - original_time > timedelta(seconds=settings.downloads_max_retry_age):
                raise DownloadRetryExhaustedError(
                    message="download has exceeded its max retry age; not re-enqueued",
                    download_id=str(stored.id),
                    error=stored.error,
                )
            stale_cutoff = now - timedelta(seconds=settings.downloads_stale_after)
            claimed = await self._downloads.claim_for_retry(stored.id, stale_cutoff)
            if claimed is not None:
                stored = claimed
                await self._enqueue(stored)
        return DownloadOut.model_validate(stored.model_dump())

    async def _enqueue(self, download: Download) -> None:
        """Push the job into SQS for a worker to pick up.

        Since the job is already added to MongoDB, we just pass the ID of the inserted document.
        """
        queue_url = get_settings().aws.sqs.download_queue_url
        try:
            await self._sqs.send_message(
                QueueUrl=queue_url,
                MessageBody=str(download.id),
            )
        except (ClientError, BotoCoreError) as err:
            await self._downloads.update_one(
                {"id": download.id},
                DownloadPatch(status=JobStatus.error, error="failed to enqueue download job"),
            )
            raise SqsError(
                message="failed to enqueue download job", download_id=str(download.id), queue_url=queue_url
            ) from err

    async def get_presigned_url(self, download_id: PydanticObjectId) -> str:
        """Generate a presigned url to download content, if the caller's file is ready.

        Raises ``NotFoundError`` when the download isn't the caller's (or doesn't exist) and
        ``JobStatusError`` when the job isn't ``ready`` yet.
        """
        bucket_name = get_settings().aws.s3.downloads_bucket

        doc = await self.read_one(download_id=download_id, fields=frozenset(["status", "s3_key"]))

        if doc is None:
            raise NotFoundError(message="download not found", download_id=str(download_id))
        if doc.status != JobStatus.ready:
            raise JobStatusError(message="download status not 'ready'", download_id=str(download_id), status=doc.status)
        if doc.s3_key is None:
            raise NotFoundError(message="download has no s3_key", download_id=str(download_id))

        try:
            url = await self._s3.generate_presigned_url(
                ClientMethod="get_object",
                Params={
                    "Bucket": bucket_name,
                    "Key": doc.s3_key,
                },
                ExpiresIn=get_settings().aws.s3.expires_in,
            )
        except (ClientError, BotoCoreError) as err:
            raise S3Error(
                message="error generating presigned url for object", object_key=doc.s3_key, bucket=bucket_name
            ) from err

        return url
