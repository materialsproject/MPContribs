"""Unit-level behaviour of ``DownloadService`` AWS error mapping.

The lifecycle (queue/dedup/retry) and the owner-scoped happy path run against a real DB in
``tests/integration/db/test_download_queue.py``. This module isolates the branches that never need a
database:

- a ``botocore`` error from the S3 client must surface as the app's ``S3Error`` (500), not leak the
  raw AWS exception (``read_one`` is stubbed so no Mongo is touched); and
- an SQS failure while enqueuing must surface as ``SqsError`` (500) *and* compensate by marking the
  just-persisted ticket ``error`` (the repository is stubbed).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from beanie import PydanticObjectId
from botocore.exceptions import BotoCoreError, ClientError

from mpcontribs_api.authz import User
from mpcontribs_api.domains.downloads.models import DownloadOut, JobStatus
from mpcontribs_api.domains.downloads.service import DownloadService
from mpcontribs_api.exceptions import NotFoundError, S3Error, SqsError


def _service() -> DownloadService:
    """A service bound to an authenticated user with fully mocked AWS clients."""
    return DownloadService(user=User(username="consumer-a"), sqs=MagicMock(), s3=MagicMock())


async def test_get_presigned_url_wraps_s3_clienterror_as_s3error():
    service = _service()
    oid = PydanticObjectId()
    # A ready ticket the caller owns: read_one is scoped in the repo, so stub it directly here.
    ready = DownloadOut(id=str(oid), status=JobStatus.ready, s3_key="contributions/deadbeef.jsonl.gz")
    service.read_one = AsyncMock(return_value=ready)  # type: ignore[method-assign]
    service._s3.head_object = AsyncMock(return_value={})  # object exists
    service._s3.generate_presigned_url = AsyncMock(
        side_effect=ClientError({"Error": {"Code": "AccessDenied", "Message": "nope"}}, "GetObject")
    )

    with pytest.raises(S3Error) as excinfo:
        await service.get_presigned_url(download_id=oid)

    # The failing object/bucket are carried on the app error for logging; the raw AWS error is chained.
    assert excinfo.value.context["object_key"] == ready.s3_key
    assert isinstance(excinfo.value.__cause__, ClientError)


async def test_get_presigned_url_returns_url_on_success():
    # Guards the sibling happy path at the unit level: a non-raising S3 client yields the signed URL
    # unwrapped, so the try/except only intercepts genuine ClientErrors.
    service = _service()
    oid = PydanticObjectId()
    service.read_one = AsyncMock(  # type: ignore[method-assign]
        return_value=DownloadOut(id=str(oid), status=JobStatus.ready, s3_key="contributions/abc.jsonl.gz")
    )
    service._s3.head_object = AsyncMock(return_value={})  # object exists
    service._s3.generate_presigned_url = AsyncMock(return_value="https://signed.example/object")

    assert await service.get_presigned_url(download_id=oid) == "https://signed.example/object"


async def test_get_presigned_url_missing_object_is_not_found():
    # A ready ticket whose S3 object is gone (lifecycle-expired before the Mongo TTL) must surface as
    # a clean 404, not a signed URL that 404s only once the client tries to fetch it.
    service = _service()
    oid = PydanticObjectId()
    service.read_one = AsyncMock(  # type: ignore[method-assign]
        return_value=DownloadOut(id=str(oid), status=JobStatus.ready, s3_key="contributions/gone.jsonl.gz")
    )
    service._s3.head_object = AsyncMock(
        side_effect=ClientError({"Error": {"Code": "404", "Message": "Not Found"}}, "HeadObject")
    )
    service._s3.generate_presigned_url = AsyncMock(return_value="https://signed.example/object")

    with pytest.raises(NotFoundError):
        await service.get_presigned_url(download_id=oid)

    # A missing object short-circuits: we never sign a URL for it.
    service._s3.generate_presigned_url.assert_not_awaited()


async def test_get_presigned_url_head_object_error_is_s3error():
    # A non-404 failure from the existence probe is an infrastructure error (500), not a 404.
    service = _service()
    oid = PydanticObjectId()
    ready = DownloadOut(id=str(oid), status=JobStatus.ready, s3_key="contributions/x.jsonl.gz")
    service.read_one = AsyncMock(return_value=ready)  # type: ignore[method-assign]
    service._s3.head_object = AsyncMock(
        side_effect=ClientError({"Error": {"Code": "AccessDenied", "Message": "nope"}}, "HeadObject")
    )
    service._s3.generate_presigned_url = AsyncMock(return_value="https://signed.example/object")

    with pytest.raises(S3Error) as excinfo:
        await service.get_presigned_url(download_id=oid)

    assert excinfo.value.context["object_key"] == ready.s3_key
    service._s3.generate_presigned_url.assert_not_awaited()


@pytest.mark.parametrize(
    "boto_error",
    [
        ClientError({"Error": {"Code": "AccessDenied", "Message": "nope"}}, "SendMessage"),
        BotoCoreError(),  # e.g. an endpoint/connection failure, not just a service-side ClientError
    ],
)
async def test_enqueue_failure_marks_ticket_error_and_raises_sqserror(boto_error):
    # A failed SQS send must not leave the ticket silently 'submitted' with no queue message. The
    # service marks it 'error' (so a re-request reclaims it immediately) and raises SqsError (500).
    service = _service()
    service._downloads = AsyncMock()  # type: ignore[assignment]
    service._sqs.send_message = AsyncMock(side_effect=boto_error)
    download = MagicMock(id=PydanticObjectId())

    with pytest.raises(SqsError) as excinfo:
        await service._enqueue(download)

    # The raw boto error is chained, and the failing ticket id is carried for logging.
    assert excinfo.value.__cause__ is boto_error
    assert excinfo.value.context["download_id"] == str(download.id)
    # Compensation: the ticket is patched to error state for its own id.
    service._downloads.update_one.assert_awaited_once()
    identifiers, patch = service._downloads.update_one.call_args.args
    assert identifiers == {"id": download.id}
    assert patch.status == JobStatus.error
    assert patch.error is not None


async def test_enqueue_success_does_not_compensate():
    # The happy path never touches the ticket: no error mark, no extra writes.
    service = _service()
    service._downloads = AsyncMock()  # type: ignore[assignment]
    service._sqs.send_message = AsyncMock(return_value={"MessageId": "m-1"})
    download = MagicMock(id=PydanticObjectId())

    await service._enqueue(download)

    service._sqs.send_message.assert_awaited_once()
    service._downloads.update_one.assert_not_awaited()
