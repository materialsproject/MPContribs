from typing import ClassVar

import structlog
from botocore.exceptions import ClientError
from pymongo.asynchronous.client_session import AsyncClientSession
from types_aiobotocore_s3 import S3Client
from types_aiobotocore_sqs.client import SQSClient

from mpcontribs_api.config import get_settings
from mpcontribs_api.domains.downloads.models import Download, DownloadIn, DownloadOut, JobStatus
from mpcontribs_api.domains.downloads.repository import MongoDbDownloadRepository
from mpcontribs_api.exceptions import JobStatusError, NotFoundError, S3Error

logger = structlog.get_logger(__name__)


class DownloadService:
    """Owns the lifecycle of an async download job.

    A job is recorded as a :class:`Download` document (so its progress can be polled) and then
    handed to a background worker via a queue. This service only persists the job and enqueues it;
    the worker that streams the results to S3 and marks the job ``ready`` lives elsewhere.
    """

    QUEUE_URL: ClassVar[str] = "some_url"

    def __init__(self, downloads: MongoDbDownloadRepository, sqs: SQSClient, s3: S3Client) -> None:
        self._downloads = downloads
        self._sqs = sqs
        self._s3 = s3

    async def read_one(
        self, s3_key: str, fields: frozenset[str], session: AsyncClientSession | None = None
    ) -> DownloadOut | None:
        identifiers = {"s3_key": s3_key}
        return await self._downloads.read_one(identifiers=identifiers, fields=fields, session=session)

    async def queue_download(self, download_in: DownloadIn) -> DownloadOut:
        """Persist a submitted download job and enqueue it for a worker to fulfil.

        The :class:`Download` document is the source of truth for job status; ``_enqueue`` only
        signals a worker to pick it up. Returns the stored job so the caller can report its id.
        """
        # TODO: Check Redis cache for s3_key first.
        # If cache hit, generate presigned url immediately. If cache miss, add to mongo and SQS
        job = Download.from_input_model(download_in)
        inserted = await self._downloads.insert_one(job)
        await self._enqueue(inserted)
        return DownloadOut.model_validate(inserted.model_dump())

    async def _enqueue(self, download: Download) -> None:
        """Push the job into SQS for a worker to pick up.

        Since the job is already added to MongoDB, we just pass the ID of the inserted document.
        """

        await self._sqs.send_message(
            QueueUrl=self.QUEUE_URL,
            MessageBody=str(download.id),
        )

    async def get_presigned_url(self, s3_key: str) -> str:
        """Genereates a presigned url to download content, if the file is ready.

        If the file is not ready, raise an error.
        """
        bucket_name = "mpcontribs-dowloads"

        doc = await self.read_one(s3_key=s3_key, fields=frozenset(["status"]))

        if doc is None:
            raise NotFoundError(message="download not found", s3_key=s3_key)
        if doc.status != JobStatus.ready:
            raise JobStatusError(message="download status not 'ready'", s3_key=s3_key, status=doc.status)

        try:
            url = await self._s3.generate_presigned_url(
                ClientMethod="get_object",
                Params={
                    "Bucket": bucket_name,
                    "Key": s3_key,
                },
                ExpiresIn=get_settings().aws.s3.expires_in,
            )
        except ClientError as err:
            raise S3Error(
                message="error generating presigned url for object", object_key=s3_key, bucket=bucket_name
            ) from err

        return url
