"""Full dev-environment E2E: a real user's download against live dev MongoDB *and* live dev AWS.

Unlike ``test_download_queue.py`` (which mocks SQS/S3), this drives the real API-side lifecycle
against a dev account: ``queue_download`` writes a ticket to dev Mongo and enqueues a real SQS
message, and ``get_presigned_url`` mints a real S3 presigned URL that is fetched over HTTP.

The download *worker* lives in another repo and is not running here, so it is **simulated**: the
test uploads the result object to the dev bucket and flips the ticket to ``ready`` itself, exactly
as the worker would, before exercising the fetch path. Everything the test creates in the dev
account (the S3 object, its SQS message) is cleaned up in a ``finally`` block; Mongo is cleaned by
the ``clean_downloads`` autouse fixture.

Gated by the ``aws`` marker + the ``aws_clients`` fixture, which skips when AWS is unconfigured or
unreachable (see ``conftest.aws_clients``). Run with: ``uv run pytest -m aws``.
"""

import asyncio
import gzip

import httpx
import pytest

from mpcontribs_api.authz import User
from mpcontribs_api.domains._shared.types import DownloadFormat
from mpcontribs_api.domains.contributions.models import ContributionFilter
from mpcontribs_api.domains.contributions.repository import MongoDbContributionRepository
from mpcontribs_api.domains.downloads.models import JobStatus
from mpcontribs_api.domains.downloads.service import DownloadService
from mpcontribs_api.exceptions import NotFoundError

pytestmark = [pytest.mark.db, pytest.mark.aws, pytest.mark.asyncio(loop_scope="session")]

OWNER = User(username="dev-e2e@example.com")
OTHER = User(username="dev-e2e-intruder@example.com")


def _contribution_query(user: User) -> dict:
    """The effective (filter AND scope) contributions query the worker would run — as the API builds it."""
    return MongoDbContributionRepository(user).build_download_query(ContributionFilter())


async def _drain_our_message(sqs, queue_url: str, body: str, *, polls: int = 3) -> bool:
    """Receive+delete the SQS message whose body is ``body``; return whether it was found.

    Assumes no competing consumer is draining this dev queue (the out-of-repo worker is not running
    against it during the test). Only messages matching our body are deleted.
    """
    for _ in range(polls):
        resp = await sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=10, WaitTimeSeconds=5)
        for msg in resp.get("Messages", []):
            if msg.get("Body") == body:
                await sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=msg["ReceiptHandle"])
                return True
    return False


async def test_real_user_download_end_to_end(db, aws_clients):
    s3, sqs = aws_clients.s3, aws_clients.sqs
    bucket, queue_url = aws_clients.bucket, aws_clients.queue_url

    # Real SQS/S3 clients on the service; the enqueue and presigned-URL calls hit the dev account.
    service = DownloadService(user=OWNER, sqs=sqs, s3=s3)

    created = await service.queue_download(
        query={"contributions": [_contribution_query(OWNER)]},
        fmt=DownloadFormat.JSONL,
    )
    s3_key = created.s3_key
    assert s3_key is not None

    payload = gzip.compress(b'{"identifier": "mp-1", "formula": "Fe2O3"}\n')
    try:
        # 1) The ticket really landed in dev Mongo, still awaiting the worker.
        stored = await db["downloads"].find_one({"requester": OWNER.username, "s3_key": s3_key})
        assert stored is not None
        assert stored["status"] == JobStatus.submitted.value

        # 2) A real SQS message carrying the ticket id was enqueued.
        assert await _drain_our_message(sqs, queue_url, str(created.id)), "download job was not enqueued to SQS"

        # 3) Simulate the (out-of-repo) worker: write the result object and mark the ticket ready.
        await s3.put_object(Bucket=bucket, Key=s3_key, Body=payload)
        await db["downloads"].update_one(
            {"requester": OWNER.username, "s3_key": s3_key},
            {"$set": {"status": JobStatus.ready.value}},
        )

        # 4) The owner fetches a real presigned URL and the bytes come back intact over HTTP.
        url = await service.get_presigned_url(download_id=created.id)
        assert url.startswith("http")
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url)
        assert resp.status_code == 200
        assert resp.content == payload

        # 5) A different authenticated user holding the id cannot fetch it (owner scope).
        intruder = DownloadService(user=OTHER, sqs=sqs, s3=s3)
        with pytest.raises(NotFoundError):
            await intruder.get_presigned_url(download_id=created.id)
    finally:
        await s3.delete_object(Bucket=bucket, Key=s3_key)
        # Best-effort: drain the message if step 2 didn't (e.g. it arrived after our poll window).
        await _drain_our_message(sqs, queue_url, str(created.id), polls=1)


async def test_dedup_shares_one_s3_object_across_requesters(db, aws_clients):
    # Two users with identical (anonymous-equivalent) scope share one physical s3_key, so the worker
    # writes the object once and both presigned URLs resolve to the same bytes. Verifies the real S3
    # dedup contract end to end: distinct tickets, one object.
    s3, sqs = aws_clients.s3, aws_clients.sqs
    bucket, queue_url = aws_clients.bucket, aws_clients.queue_url

    svc_a = DownloadService(user=OWNER, sqs=sqs, s3=s3)
    svc_b = DownloadService(user=OTHER, sqs=sqs, s3=s3)
    # identical (public-only) scope for both requesters
    query = {"contributions": [_contribution_query(User())]}
    a = await svc_a.queue_download(query=query, fmt=DownloadFormat.JSONL)
    b = await svc_b.queue_download(query=query, fmt=DownloadFormat.JSONL)

    payload = gzip.compress(b'{"identifier": "mp-2"}\n')
    try:
        assert a.id != b.id  # per-requester tickets
        assert a.s3_key == b.s3_key  # ...but one shared physical object

        await s3.put_object(Bucket=bucket, Key=a.s3_key, Body=payload)
        for svc, ticket in ((svc_a, a), (svc_b, b)):
            await db["downloads"].update_one(
                {"requester": svc._user.username, "s3_key": ticket.s3_key},
                {"$set": {"status": JobStatus.ready.value}},
            )
            url = await svc.get_presigned_url(download_id=ticket.id)
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(url)
            assert resp.status_code == 200 and resp.content == payload
    finally:
        assert a.s3_key is not None
        await s3.delete_object(Bucket=bucket, Key=a.s3_key)
        await asyncio.gather(
            _drain_our_message(sqs, queue_url, str(a.id), polls=1),
            _drain_our_message(sqs, queue_url, str(b.id), polls=1),
        )
