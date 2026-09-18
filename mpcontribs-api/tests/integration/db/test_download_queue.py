"""End-to-end (real-DB) behaviour of the download-ticket lifecycle.

Covers the Ticket model: one Mongo row per ``(requester, s3_key)``, ``queue_download`` idempotent
and enqueueing only on a genuinely new (or retried) ticket, per-requester isolation with shared
``s3_key`` (so S3 can dedupe the physical object), and the caller-scoped read/fetch path.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from mpcontribs_api.authz import User
from mpcontribs_api.domains._shared.types import DownloadFormat
from mpcontribs_api.domains.contributions.models import ContributionFilter
from mpcontribs_api.domains.contributions.repository import MongoDbContributionRepository
from mpcontribs_api.domains.downloads.models import DownloadIn, JobStatus
from mpcontribs_api.domains.downloads.service import DownloadService
from mpcontribs_api.exceptions import JobStatusError

pytestmark = [pytest.mark.db, pytest.mark.asyncio(loop_scope="session")]

# Callers spanning two visibility buckets: an admin (unscoped) and an anonymous user (public only).
ADMIN = User(username="google:admin@example.com", groups=frozenset({"admin"}))
ANON = User()


def _service() -> tuple[DownloadService, MagicMock]:
    """A DownloadService with an async-mocked SQS and S3 client, plus a handle on the SQS mock."""
    sqs = MagicMock()
    sqs.send_message = AsyncMock()
    service = DownloadService(user=User(), sqs=sqs, s3=MagicMock())
    return service, sqs


def _user(requester: str) -> User:
    """A caller whose ``requester_id`` resolves to ``requester``."""
    return User(consumer_id=requester)


def _query(scope_user: User, **filter_kwargs) -> dict:
    """The effective Mongo query (filter AND read scope) exactly as the source domain builds it."""
    return MongoDbContributionRepository(scope_user).build_download_query(ContributionFilter(**filter_kwargs))


def _download_in(
    requester: str,
    *,
    scope_user: User = ANON,
    fmt: DownloadFormat = DownloadFormat.JSONL,
    **filter_kwargs,
) -> DownloadIn:
    """A download request whose ``query`` carries ``scope_user``'s visibility (anonymous by default)."""
    return DownloadIn(
        status=JobStatus.submitted,
        requester=requester,
        query=_query(scope_user, **filter_kwargs),
        domain="contributions",
        fmt=fmt,
    )


class TestQueueIdempotency:
    async def test_identical_resubmit_reuses_ticket_and_enqueues_once(self, db):
        service, sqs = _service()
        first = await service.queue_download(_download_in("consumer-a"))
        second = await service.queue_download(_download_in("consumer-a"))

        # Same ticket returned both times, only one row, only one enqueue.
        assert first.id == second.id
        assert first.s3_key == second.s3_key
        assert sqs.send_message.await_count == 1
        assert await db["downloads"].count_documents({}) == 1

    async def test_different_requesters_get_separate_tickets_but_share_s3_key(self, db):
        service, sqs = _service()
        out_a = await service.queue_download(_download_in("consumer-a"))
        out_b = await service.queue_download(_download_in("consumer-b"))

        # Two distinct tickets (per-requester), each enqueued once...
        assert out_a.id != out_b.id
        assert await db["downloads"].count_documents({}) == 2
        assert sqs.send_message.await_count == 2
        # ...but the same physical object key: both callers have identical (anonymous) scope, so their
        # effective queries match and S3 can safely dedupe the bytes. Scope equality is now *enforced*
        # by folding scope into the query (see TestScopeIsolation), not merely assumed.
        assert out_a.s3_key == out_b.s3_key

    async def test_distinct_requests_produce_distinct_tickets(self, db):
        service, sqs = _service()
        jsonl = await service.queue_download(_download_in("consumer-a", fmt=DownloadFormat.JSONL))
        csv = await service.queue_download(_download_in("consumer-a", fmt=DownloadFormat.CSV))
        filtered = await service.queue_download(_download_in("consumer-a", material_id="mp-1"))

        assert len({jsonl.s3_key, csv.s3_key, filtered.s3_key}) == 3
        assert await db["downloads"].count_documents({}) == 3
        assert sqs.send_message.await_count == 3


class TestScopeIsolation:
    """The s3_key must isolate callers who see different rows, and only those callers."""

    async def test_build_download_query_reflects_scope(self, db):
        # Admin is unscoped; the anonymous caller is restricted to public rows. Same filter, so any
        # difference in the effective query is purely the access scope.
        admin_query = _query(ADMIN)
        anon_query = _query(ANON)
        assert admin_query != anon_query
        assert admin_query == {}  # admin bypasses read scope entirely
        assert "is_public" in repr(anon_query)  # anonymous callers are pinned to public data

    async def test_different_scope_same_filter_gets_distinct_s3_key(self, db):
        # Regression: previously the s3_key hashed only the raw filter, so these two callers collided
        # on one physical object and the anonymous caller could receive admin-scoped bytes.
        service, sqs = _service()
        admin_out = await service.queue_download(_download_in("admin-consumer", scope_user=ADMIN))
        anon_out = await service.queue_download(_download_in("anon-consumer", scope_user=ANON))

        assert admin_out.s3_key != anon_out.s3_key
        assert await db["downloads"].count_documents({}) == 2
        assert sqs.send_message.await_count == 2

    async def test_same_scope_and_filter_shares_s3_key(self, db):
        # The dedup contract still holds for callers who would see the same rows.
        service, _ = _service()
        first = await service.queue_download(_download_in("consumer-a", scope_user=ANON))
        second = await service.queue_download(_download_in("consumer-b", scope_user=ANON))
        assert first.s3_key == second.s3_key


class TestRetryOnError:
    async def test_errored_ticket_is_reset_and_re_enqueued(self, db):
        service, sqs = _service()
        created = await service.queue_download(_download_in("consumer-a"))
        assert sqs.send_message.await_count == 1

        # Simulate a worker failure on the ticket.
        await db["downloads"].update_one(
            {"requester": "consumer-a", "s3_key": created.s3_key},
            {"$set": {"status": JobStatus.error.value, "error": "boom", "rows_written": 3}},
        )

        retried = await service.queue_download(_download_in("consumer-a"))

        assert retried.status == JobStatus.submitted
        assert sqs.send_message.await_count == 2  # re-enqueued
        assert await db["downloads"].count_documents({}) == 1  # still one ticket
        stored = await db["downloads"].find_one({"requester": "consumer-a", "s3_key": created.s3_key})
        assert stored is not None
        assert stored["status"] == JobStatus.submitted.value
        assert stored.get("error") is None  # prior failure cleared
        assert stored["rows_written"] == 0

    async def test_ready_ticket_is_returned_without_re_enqueue(self, db):
        service, sqs = _service()
        created = await service.queue_download(_download_in("consumer-a"))
        await db["downloads"].update_one(
            {"requester": "consumer-a", "s3_key": created.s3_key},
            {"$set": {"status": JobStatus.ready.value}},
        )

        again = await service.queue_download(_download_in("consumer-a"))

        assert again.status == JobStatus.ready
        assert sqs.send_message.await_count == 1  # unchanged: no work to do


class TestReadAndFetch:
    async def test_read_one_is_scoped_to_the_caller(self, db):
        service, _ = _service()
        created = await service.queue_download(_download_in("consumer-a"))

        mine = await service.read_one(user=_user("consumer-a"), s3_key=created.s3_key)
        assert mine is not None and mine.s3_key == created.s3_key
        # Another caller derives the same s3_key but has no ticket of their own for it.
        assert await service.read_one(user=_user("consumer-b"), s3_key=created.s3_key) is None

    async def test_presigned_url_requires_ready_status(self, db):
        service, _ = _service()
        created = await service.queue_download(_download_in("consumer-a"))
        caller = _user("consumer-a")

        # Freshly submitted: not ready yet.
        with pytest.raises(JobStatusError):
            await service.get_presigned_url(user=caller, s3_key=created.s3_key)

        await db["downloads"].update_one(
            {"requester": "consumer-a", "s3_key": created.s3_key},
            {"$set": {"status": JobStatus.ready.value}},
        )
        service._s3.generate_presigned_url = AsyncMock(return_value="https://signed.example/object")
        url = await service.get_presigned_url(user=caller, s3_key=created.s3_key)
        assert url == "https://signed.example/object"
