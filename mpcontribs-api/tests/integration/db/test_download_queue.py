"""End-to-end (real-DB) behaviour of the download-ticket lifecycle.

Covers the Ticket model: one Mongo row per ``(requester, s3_key)``, ``queue_download`` idempotent
and enqueueing only on a genuinely new (or retried) ticket, per-requester isolation with shared
``s3_key`` (so S3 can dedupe the physical object), and the caller-scoped read/fetch path.

``queue_download`` takes only ``query`` + ``domain`` + ``fmt``; the requester is the service's own
authenticated user, so a submission "as" a given requester binds the service to that user.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from mpcontribs_api.authz import User
from mpcontribs_api.domains._shared.types import DownloadFormat
from mpcontribs_api.domains.contributions.models import ContributionFilter
from mpcontribs_api.domains.contributions.repository import MongoDbContributionRepository
from mpcontribs_api.domains.downloads.models import DownloadDomain, DownloadOut, JobStatus
from mpcontribs_api.domains.downloads.service import DownloadService
from mpcontribs_api.exceptions import JobStatusError, NotFoundError, PermissionError

pytestmark = [pytest.mark.db, pytest.mark.asyncio(loop_scope="session")]

# Callers spanning two visibility buckets: an admin (unscoped) and an anonymous user (public only).
ADMIN = User(username="google:admin@example.com", groups=frozenset({"admin"}))
ANON = User()


def _owner(username: str) -> User:
    """An authenticated caller who owns downloads recorded under ``requester == username``."""
    return User(username=username)


def _service(user: User | None = None) -> tuple[DownloadService, MagicMock]:
    """A DownloadService with an async-mocked SQS and S3 client, plus a handle on the SQS mock.

    ``user`` is the authenticated caller the service is bound to; ``queue_download`` records
    ``requester`` straight from that user. Defaults to an arbitrary authenticated user.
    """
    sqs = MagicMock()
    sqs.send_message = AsyncMock()
    service = DownloadService(user=user or _owner("requester@example.com"), sqs=sqs, s3=MagicMock())
    return service, sqs


def _query(scope_user: User, **filter_kwargs) -> dict:
    """The effective Mongo query (filter AND read scope) exactly as the source domain builds it."""
    return MongoDbContributionRepository(scope_user).build_download_query(ContributionFilter(**filter_kwargs))


async def _queue(
    service: DownloadService,
    *,
    scope_user: User = ANON,
    fmt: DownloadFormat = DownloadFormat.JSONL,
    **filter_kwargs,
) -> DownloadOut:
    """Submit a contributions download whose ``query`` carries ``scope_user``'s visibility.

    The requester is the ``service``'s bound user; ``scope_user`` only shapes the query (anonymous
    by default).
    """
    return await service.queue_download(
        query=_query(scope_user, **filter_kwargs),
        domain=DownloadDomain.contributions,
        fmt=fmt,
    )


class TestQueueIdempotency:
    async def test_identical_resubmit_reuses_ticket_and_enqueues_once(self, db):
        service, sqs = _service(_owner("consumer-a"))
        first = await _queue(service)
        second = await _queue(service)

        # Same ticket returned both times, only one row, only one enqueue.
        assert first.id == second.id
        assert first.s3_key == second.s3_key
        assert sqs.send_message.await_count == 1
        assert await db["downloads"].count_documents({}) == 1

    async def test_different_requesters_get_separate_tickets_but_share_s3_key(self, db):
        service_a, sqs_a = _service(_owner("consumer-a"))
        service_b, sqs_b = _service(_owner("consumer-b"))
        out_a = await _queue(service_a)
        out_b = await _queue(service_b)

        # Two distinct tickets (per-requester), each enqueued once...
        assert out_a.id != out_b.id
        assert await db["downloads"].count_documents({}) == 2
        assert sqs_a.send_message.await_count == 1
        assert sqs_b.send_message.await_count == 1
        # ...but the same physical object key: both callers have identical (anonymous) scope, so their
        # effective queries match and S3 can safely dedupe the bytes. Scope equality is now *enforced*
        # by folding scope into the query (see TestScopeIsolation), not merely assumed.
        assert out_a.s3_key == out_b.s3_key

    async def test_distinct_requests_produce_distinct_tickets(self, db):
        service, sqs = _service(_owner("consumer-a"))
        jsonl = await _queue(service, fmt=DownloadFormat.JSONL)
        csv = await _queue(service, fmt=DownloadFormat.CSV)
        filtered = await _queue(service, material_id="mp-1")

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
        service_admin, sqs_admin = _service(_owner("admin-consumer"))
        service_anon, sqs_anon = _service(_owner("anon-consumer"))
        admin_out = await _queue(service_admin, scope_user=ADMIN)
        anon_out = await _queue(service_anon, scope_user=ANON)

        assert admin_out.s3_key != anon_out.s3_key
        assert await db["downloads"].count_documents({}) == 2
        assert sqs_admin.send_message.await_count == 1
        assert sqs_anon.send_message.await_count == 1

    async def test_same_scope_and_filter_shares_s3_key(self, db):
        # The dedup contract still holds for callers who would see the same rows.
        service_a, _ = _service(_owner("consumer-a"))
        service_b, _ = _service(_owner("consumer-b"))
        first = await _queue(service_a, scope_user=ANON)
        second = await _queue(service_b, scope_user=ANON)
        assert first.s3_key == second.s3_key


class TestAnonymousRejected:
    async def test_anonymous_caller_cannot_queue_download(self, db):
        # The requester is the service's user; an anonymous service (no username) has no owner to
        # record the ticket under, so the guard now lives in DownloadService itself.
        service, sqs = _service(ANON)
        with pytest.raises(PermissionError):
            await _queue(service)
        assert sqs.send_message.await_count == 0
        assert await db["downloads"].count_documents({}) == 0


class TestRetryOnError:
    async def test_errored_ticket_is_reset_and_re_enqueued(self, db):
        service, sqs = _service(_owner("consumer-a"))
        created = await _queue(service)
        assert sqs.send_message.await_count == 1

        # Simulate a worker failure on the ticket.
        await db["downloads"].update_one(
            {"requester": "consumer-a", "s3_key": created.s3_key},
            {"$set": {"status": JobStatus.error.value, "error": "boom", "rows_written": 3}},
        )

        retried = await _queue(service)

        assert retried.status == JobStatus.submitted
        assert sqs.send_message.await_count == 2  # re-enqueued
        assert await db["downloads"].count_documents({}) == 1  # still one ticket
        stored = await db["downloads"].find_one({"requester": "consumer-a", "s3_key": created.s3_key})
        assert stored is not None
        assert stored["status"] == JobStatus.submitted.value
        assert stored.get("error") is None  # prior failure cleared
        assert stored["rows_written"] == 0

    async def test_ready_ticket_is_returned_without_re_enqueue(self, db):
        service, sqs = _service(_owner("consumer-a"))
        created = await _queue(service)
        await db["downloads"].update_one(
            {"requester": "consumer-a", "s3_key": created.s3_key},
            {"$set": {"status": JobStatus.ready.value}},
        )

        again = await _queue(service)

        assert again.status == JobStatus.ready
        assert sqs.send_message.await_count == 1  # unchanged: no work to do


class TestReadAndFetch:
    async def test_read_one_is_scoped_to_the_caller(self, db):
        # The download is owned by ``consumer-a`` (requester == username); the service reads through
        # the repo's owner scope, so only that user resolves the ticket — by its ``_id`` handle.
        service, _ = _service(_owner("consumer-a"))
        created = await _queue(service)

        mine = await service.read_one(download_id=created.id)
        assert mine is not None and mine.s3_key == created.s3_key
        # Another caller cannot read it, even holding the id.
        other, _ = _service(_owner("consumer-b"))
        assert await other.read_one(download_id=created.id) is None

    async def test_get_presigned_url_not_found_for_non_owner(self, db):
        # A ready download of consumer-a's must not be fetchable by another user who knows its id.
        service, _ = _service(_owner("consumer-a"))
        created = await _queue(service)
        await db["downloads"].update_one(
            {"requester": "consumer-a", "s3_key": created.s3_key},
            {"$set": {"status": JobStatus.ready.value}},
        )

        other, _ = _service(_owner("consumer-b"))
        with pytest.raises(NotFoundError):
            await other.get_presigned_url(download_id=created.id)

    async def test_presigned_url_requires_ready_status(self, db):
        service, _ = _service(_owner("consumer-a"))
        created = await _queue(service)

        # Freshly submitted: not ready yet.
        with pytest.raises(JobStatusError):
            await service.get_presigned_url(download_id=created.id)

        await db["downloads"].update_one(
            {"requester": "consumer-a", "s3_key": created.s3_key},
            {"$set": {"status": JobStatus.ready.value}},
        )
        service._s3.generate_presigned_url = AsyncMock(return_value="https://signed.example/object")
        url = await service.get_presigned_url(download_id=created.id)
        assert url == "https://signed.example/object"
