from typing import ClassVar

import structlog
from pymongo.asynchronous.client_session import AsyncClientSession
from types_aiobotocore_sqs.client import SQSClient

from mpcontribs_api.domains.downloads.models import Download, DownloadIn, DownloadOut
from mpcontribs_api.domains.downloads.repository import MongoDbDownloadRepository

logger = structlog.get_logger(__name__)


class DownloadService:
    """Owns the lifecycle of an async download job.

    A job is recorded as a :class:`Download` document (so its progress can be polled) and then
    handed to a background worker via a queue. This service only persists the job and enqueues it;
    the worker that streams the results to S3 and marks the job ``ready`` lives elsewhere.
    """

    QUEUE_URL: ClassVar[str] = "some_url"

    def __init__(self, downloads: MongoDbDownloadRepository, sqs: SQSClient) -> None:
        self._downloads = downloads
        self._sqs = sqs

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
        # TODO: Implement. Left as stub method to silence errors
        return ""
