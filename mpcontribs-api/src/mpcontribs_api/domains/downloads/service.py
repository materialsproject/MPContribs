import structlog
from botocore.exceptions import ClientError
from pymongo.asynchronous.client_session import AsyncClientSession
from types_aiobotocore_s3 import S3Client
from types_aiobotocore_sqs.client import SQSClient

from mpcontribs_api.authz import User
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

    def __init__(self, downloads: MongoDbDownloadRepository, sqs: SQSClient, s3: S3Client) -> None:
        self._downloads = downloads
        self._sqs = sqs
        self._s3 = s3

    async def read_one(
        self, user: User, s3_key: str, fields: frozenset[str] | None = None, session: AsyncClientSession | None = None
    ) -> DownloadOut | None:
        identifiers = {"requester": user.requester_id, "s3_key": s3_key}
        return await self._downloads.read_one(identifiers=identifiers, fields=fields, session=session)

    async def queue_download(self, download_in: DownloadIn) -> DownloadOut:
        """Insert a Download document and add download job to queue if it is a new job.

        If the job was created for the first time now, or if the previous job has the status `JobStatus.error`,
        add the job to the queue, otherwise return the document.
        """
        job = Download.from_input_model(download_in)
        stored, created = await self._downloads.insert_or_get(job)
        # if the job is newly created, or is retrying a failed job, add it to the queue
        if created:
            await self._enqueue(stored)
        elif stored.status == JobStatus.error:
            claimed = await self._downloads.claim_error_for_retry(stored.id)
            if claimed is not None:
                stored = claimed
                await self._enqueue(stored)
        return DownloadOut.model_validate(stored.model_dump())

    async def _enqueue(self, download: Download) -> None:
        """Push the job into SQS for a worker to pick up.

        Since the job is already added to MongoDB, we just pass the ID of the inserted document.
        """

        await self._sqs.send_message(
            QueueUrl=get_settings().aws.sqs.download_queue_url,
            MessageBody=str(download.id),
        )

    async def get_presigned_url(self, user: User, s3_key: str) -> str:
        """Genereates a presigned url to download content, if the file is ready.

        If the file is not ready, raise an error.
        """
        bucket_name = get_settings().aws.s3.downloads_bucket

        doc = await self.read_one(user=user, s3_key=s3_key, fields=frozenset(["status"]))

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
