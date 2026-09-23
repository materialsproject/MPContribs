"""Unit-level behaviour of ``DownloadService.get_presigned_url`` error mapping.

The lifecycle (queue/dedup/retry) and the owner-scoped happy path run against a real DB in
``tests/integration/db/test_download_queue.py``. This module isolates the one branch that never
needs a database: a ``botocore`` ``ClientError`` from the S3 client must surface as the app's
``S3Error`` (500), not leak the raw AWS exception. ``read_one`` is stubbed so no Mongo is touched.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from beanie import PydanticObjectId
from botocore.exceptions import ClientError

from mpcontribs_api.authz import User
from mpcontribs_api.domains.downloads.models import DownloadOut, JobStatus
from mpcontribs_api.domains.downloads.service import DownloadService
from mpcontribs_api.exceptions import S3Error


def _service() -> DownloadService:
    """A service bound to an authenticated user with fully mocked AWS clients."""
    return DownloadService(user=User(username="consumer-a"), sqs=MagicMock(), s3=MagicMock())


async def test_get_presigned_url_wraps_s3_clienterror_as_s3error():
    service = _service()
    oid = PydanticObjectId()
    # A ready ticket the caller owns: read_one is scoped in the repo, so stub it directly here.
    ready = DownloadOut(id=str(oid), status=JobStatus.ready, s3_key="contributions/deadbeef.jsonl.gz")
    service.read_one = AsyncMock(return_value=ready)  # type: ignore[method-assign]
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
    service._s3.generate_presigned_url = AsyncMock(return_value="https://signed.example/object")

    assert await service.get_presigned_url(download_id=oid) == "https://signed.example/object"
