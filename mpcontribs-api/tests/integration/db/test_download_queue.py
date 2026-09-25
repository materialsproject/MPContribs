"""End-to-end (real-DB) behaviour of the download-ticket lifecycle.

Covers the Ticket model: one Mongo row per ``(requester, s3_key)``, ``queue_download`` idempotent
and enqueueing only on a genuinely new (or retried) ticket, per-requester isolation with shared
``s3_key`` (so S3 can dedupe the physical object), and the caller-scoped read/fetch path.

``queue_download`` takes only ``query`` + ``fmt``; the requester is the service's own authenticated
user, so a submission "as" a given requester binds the service to that user. ``query`` is the
``{collection: [mongo_query]}`` map the worker runs (a contribution-only download here is
``{"contributions": [<scoped query>]}``).
"""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from mpcontribs_api.authz import User
from mpcontribs_api.config import get_settings
from mpcontribs_api.domains._shared.types import DownloadFormat
from mpcontribs_api.domains.contributions.models import ContributionFilter
from mpcontribs_api.domains.contributions.repository import MongoDbContributionRepository
from mpcontribs_api.domains.downloads.models import DownloadOut, JobStatus
from mpcontribs_api.domains.downloads.service import DownloadService
from mpcontribs_api.exceptions import (
    DownloadLimitError,
    DownloadRetryExhaustedError,
    JobStatusError,
    NotFoundError,
    PermissionError,
)

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
    s3 = MagicMock()
    # Async-mock the awaited S3 calls so a bare MagicMock isn't awaited; the object-exists probe
    # defaults to "present" and individual tests override generate_presigned_url as needed.
    s3.head_object = AsyncMock(return_value={})
    s3.generate_presigned_url = AsyncMock(return_value="https://signed.example/object")
    service = DownloadService(user=user or _owner("requester@example.com"), sqs=sqs, s3=s3)
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
        query={"contributions": [_query(scope_user, **filter_kwargs)]},
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


class TestConcurrentFirstSubmit:
    """P4 #15: the single-enqueue dedup guarantee under two callers racing the *first* submission.

    ``insert_or_get`` upserts on the unique ``(requester, s3_key)`` index, so exactly one caller
    performs the insert (``created=True`` -> enqueues) and the other must observe the already-stored
    ticket (``created=False`` -> no enqueue). Two identical concurrent requests therefore yield one
    row and one SQS message, never two.
    """

    async def test_two_callers_racing_first_submit_enqueue_once(self, db):
        # Same requester + identical query => identical natural key => a genuine insert race.
        service_a, sqs_a = _service(_owner("consumer-a"))
        service_b, sqs_b = _service(_owner("consumer-a"))

        out_a, out_b = await asyncio.gather(_queue(service_a), _queue(service_b))

        # One physical ticket, handed back to both callers...
        assert out_a.id == out_b.id
        assert await db["downloads"].count_documents({}) == 1
        # ...and enqueued exactly once across the two racing callers (the loser must not re-enqueue).
        assert sqs_a.send_message.await_count + sqs_b.send_message.await_count == 1


class TestReadySiblingAdoption:
    """A new ticket adopts an already-``ready`` object for the same s3_key instead of re-running.

    The s3_key embeds the caller's read scope, so a ready ticket sharing it was produced under an
    identical scoped query — the same data the new caller is entitled to. The new ticket is served
    ``ready`` immediately, the worker is not re-invoked, and the byte/row counts are copied so the
    returned metadata stays accurate.
    """

    async def test_new_requester_adopts_ready_object_without_enqueue(self, db):
        # consumer-a's job has finished; consumer-b then requests the identical (anonymous) scope.
        service_a, _ = _service(_owner("consumer-a"))
        ready = await _queue(service_a)
        await db["downloads"].update_one(
            {"requester": "consumer-a", "s3_key": ready.s3_key},
            {"$set": {"status": JobStatus.ready.value, "rows_written": 42, "bytes_written": 1024}},
        )

        service_b, sqs_b = _service(_owner("consumer-b"))
        out_b = await _queue(service_b)

        # b's ticket is served ready straight away, with no duplicate worker job...
        assert out_b.status == JobStatus.ready
        assert sqs_b.send_message.await_count == 0
        # ...its counts copied from the sibling so the metadata is accurate...
        assert (out_b.rows_written, out_b.bytes_written) == (42, 1024)
        # ...and it is b's own row (per-requester), sharing a's physical object key.
        assert out_b.s3_key == ready.s3_key
        b_doc = await db["downloads"].find_one({"requester": "consumer-b", "s3_key": ready.s3_key})
        assert b_doc is not None and b_doc["status"] == JobStatus.ready.value

    async def test_no_adoption_while_sibling_still_in_flight(self, db):
        # A sibling that is only ``submitted`` (worker hasn't finished) is not adoptable: b still
        # enqueues its own job rather than being handed an object that doesn't exist yet.
        service_a, _ = _service(_owner("consumer-a"))
        await _queue(service_a)  # stays 'submitted' (worker is mocked)

        service_b, sqs_b = _service(_owner("consumer-b"))
        out_b = await _queue(service_b)

        assert out_b.status == JobStatus.submitted
        assert sqs_b.send_message.await_count == 1

    async def test_adopted_ticket_does_not_consume_active_cap(self, db, monkeypatch):
        # An instantly-adopted ticket costs no worker capacity, so it must not count against the cap:
        # consumer-b sitting at the cap can still adopt a ready object.
        monkeypatch.setattr(get_settings().mpcontribs, "downloads_max_active", 2)
        service_a, _ = _service(_owner("consumer-a"))
        ready = await _queue(service_a)
        await db["downloads"].update_one(
            {"requester": "consumer-a", "s3_key": ready.s3_key},
            {"$set": {"status": JobStatus.ready.value}},
        )

        service_b, _ = _service(_owner("consumer-b"))
        # Fill consumer-b's cap with distinct in-flight tickets.
        await _queue(service_b, material_id="mp-0")
        await _queue(service_b, material_id="mp-1")
        assert await db["downloads"].count_documents(
            {"requester": "consumer-b", "status": JobStatus.submitted.value}
        ) == 2

        # The adoptable request is satisfied despite b being at the cap (it never enters 'in flight').
        adopted = await _queue(service_b)
        assert adopted.status == JobStatus.ready


class TestScopeIsolation:
    """The s3_key must isolate callers who see different rows, and only those callers."""

    async def test_build_download_query_reflects_scope(self, db):
        # Admin is unscoped; the anonymous caller is restricted to public rows. Same filter, so any
        # difference in the effective query is purely the access scope.
        admin_query = _query(ADMIN)
        anon_query = _query(ANON)
        assert admin_query != anon_query
        assert admin_query == {}  # admin bypasses read scope entirely
        # Structural, not a repr substring: the anonymous contributions scope is exactly the public
        # clause (see MongoDbContributionRepository.read_scope = Scope(Public(), Granted(...)); the
        # Granted clause drops out for a caller with no grants). Public() has approved=False, so no
        # is_approved term — asserting the whole dict pins both the field and the shape.
        assert anon_query == {"$or": [{"is_public": True}]}

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


class TestBundleShapePartitionsKey:
    """The query map (which collections are bundled) partitions the s3_key.

    ``domain`` was removed; a download's collections now live in the ``query`` keys, so two requests
    that differ only in which collections they bundle — or in a per-level filter — must land on
    distinct physical objects, and identical bundles must share one.
    """

    async def test_including_a_related_collection_changes_the_key(self, db):
        service, _ = _service(_owner("consumer-a"))
        base = await service.queue_download(query={"contributions": [{"$or": [{"is_public": True}]}]}, fmt=DownloadFormat.JSONL)
        bundled = await service.queue_download(
            query={"contributions": [{"$or": [{"is_public": True}]}], "structures": [{}]},
            fmt=DownloadFormat.JSONL,
        )
        assert base.s3_key != bundled.s3_key
        assert await db["downloads"].count_documents({}) == 2

    async def test_per_level_filter_changes_the_key(self, db):
        service, _ = _service(_owner("consumer-a"))
        unfiltered = await service.queue_download(
            query={"contributions": [{}], "structures": [{}]}, fmt=DownloadFormat.JSONL
        )
        filtered = await service.queue_download(
            query={"contributions": [{}], "structures": [{"name": "POSCAR"}]}, fmt=DownloadFormat.JSONL
        )
        assert unfiltered.s3_key != filtered.s3_key

    async def test_identical_bundle_shares_the_key(self, db):
        service_a, _ = _service(_owner("consumer-a"))
        service_b, _ = _service(_owner("consumer-b"))
        query = {"contributions": [{"$or": [{"is_public": True}]}], "tables": [{}]}
        first = await service_a.queue_download(query=query, fmt=DownloadFormat.JSONL)
        second = await service_b.queue_download(query=query, fmt=DownloadFormat.JSONL)
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


class TestActiveLimit:
    """A user may have at most ``downloads_max_active`` unfinished (``submitted``) jobs at once.

    Enforced only when a genuinely new ticket is created, so a cache hit or an idempotent re-request
    of an existing in-flight ticket is never blocked. The cap is per-requester.
    """

    @pytest.fixture
    def cap(self, monkeypatch):
        """Shrink the in-flight cap to 2 for the duration of a test (restored automatically)."""
        monkeypatch.setattr(get_settings().mpcontribs, "downloads_max_active", 2)
        return 2

    async def test_new_submission_over_cap_is_refused_and_rolled_back(self, db, cap):
        service, sqs = _service(_owner("consumer-a"))
        # Two distinct in-flight tickets fill the cap.
        await _queue(service, fmt=DownloadFormat.JSONL)
        await _queue(service, fmt=DownloadFormat.CSV)
        assert sqs.send_message.await_count == 2
        assert await db["downloads"].count_documents({}) == 2

        # A third, distinct submission trips the cap: refused, with no orphan ticket and no enqueue.
        with pytest.raises(DownloadLimitError):
            await _queue(service, material_id="mp-1")

        assert await db["downloads"].count_documents({}) == 2  # the over-cap ticket was rolled back
        assert sqs.send_message.await_count == 2  # not enqueued

    async def test_existing_in_flight_rerequest_is_not_blocked(self, db, cap):
        # An idempotent re-request of an already-``submitted`` ticket is not a new ticket, so it is
        # returned as-is even when the requester is at the cap.
        service, sqs = _service(_owner("consumer-a"))
        first = await _queue(service, fmt=DownloadFormat.JSONL)
        await _queue(service, fmt=DownloadFormat.CSV)  # now at cap (2 submitted)

        again = await _queue(service, fmt=DownloadFormat.JSONL)

        assert again.id == first.id
        assert await db["downloads"].count_documents({}) == 2
        assert sqs.send_message.await_count == 2  # unchanged: no new work

    async def test_ready_ticket_is_retrievable_at_cap(self, db, cap):
        # A finished (``ready``) job doesn't count toward the cap and a re-request returns it (cache
        # hit) rather than being blocked, even while the requester's other jobs sit at the cap.
        service, sqs = _service(_owner("consumer-a"))
        ready = await _queue(service, fmt=DownloadFormat.JSONL)
        await db["downloads"].update_one(
            {"requester": "consumer-a", "s3_key": ready.s3_key},
            {"$set": {"status": JobStatus.ready.value}},
        )
        # Fill the cap with distinct in-flight tickets.
        await _queue(service, fmt=DownloadFormat.CSV)
        await _queue(service, material_id="mp-1")
        assert await db["downloads"].count_documents({"status": JobStatus.submitted.value}) == 2

        hit = await _queue(service, fmt=DownloadFormat.JSONL)
        assert hit.status == JobStatus.ready  # cache hit, not refused

    async def test_cap_is_per_requester(self, db, cap):
        # consumer-a at the cap does not stop consumer-b from queuing their own downloads.
        service_a, _ = _service(_owner("consumer-a"))
        await _queue(service_a, fmt=DownloadFormat.JSONL)
        await _queue(service_a, fmt=DownloadFormat.CSV)  # consumer-a now at cap
        with pytest.raises(DownloadLimitError):
            await _queue(service_a, material_id="mp-1")

        service_b, sqs_b = _service(_owner("consumer-b"))
        out_b = await _queue(service_b, fmt=DownloadFormat.JSONL)  # must not raise
        assert out_b.status == JobStatus.submitted
        assert sqs_b.send_message.await_count == 1

    async def test_working_jobs_count_toward_cap(self, db, cap):
        # A job a worker has already picked up (``working``) is still in flight and counts against the
        # cap, so it isn't a loophole for exceeding it once work starts.
        service, _ = _service(_owner("consumer-a"))
        first = await _queue(service, fmt=DownloadFormat.JSONL)
        await _queue(service, fmt=DownloadFormat.CSV)
        # A worker claims the first job: submitted -> working. Still 2 in flight (1 working, 1 submitted).
        await db["downloads"].update_one(
            {"requester": "consumer-a", "s3_key": first.s3_key},
            {"$set": {"status": JobStatus.working.value}},
        )

        with pytest.raises(DownloadLimitError):
            await _queue(service, material_id="mp-1")


class TestRetryOnError:
    async def test_errored_ticket_is_reset_and_re_enqueued(self, db):
        service, sqs = _service(_owner("consumer-a"))
        created = await _queue(service)
        assert sqs.send_message.await_count == 1

        # Simulate a worker failure on the ticket, and age its clock so the retry's ``created_at``
        # bump is observable (#11: a re-run must restart the TTL clock, not inherit the old one).
        stale_clock = datetime.now(UTC) - timedelta(hours=6)
        await db["downloads"].update_one(
            {"requester": "consumer-a", "s3_key": created.s3_key},
            {"$set": {"status": JobStatus.error.value, "error": "boom", "rows_written": 3, "created_at": stale_clock}},
        )
        before = await db["downloads"].find_one({"requester": "consumer-a", "s3_key": created.s3_key})
        assert before is not None
        original_time_before = before["original_time"]

        retried = await _queue(service)

        assert retried.status == JobStatus.submitted
        assert sqs.send_message.await_count == 2  # re-enqueued
        assert await db["downloads"].count_documents({}) == 1  # still one ticket
        stored = await db["downloads"].find_one({"requester": "consumer-a", "s3_key": created.s3_key})
        assert stored is not None
        assert stored["status"] == JobStatus.submitted.value
        assert stored.get("error") is None  # prior failure cleared
        assert stored["rows_written"] == 0
        # #11: TTL/retry clock restarted, so a re-run can't expire mid-flight...
        assert stored["created_at"] > before["created_at"]
        # ...while the immutable birth time is preserved across the retry.
        assert stored["original_time"] == original_time_before

    async def test_original_time_is_set_once_and_survives_retry(self, db):
        # At insert, birth time and TTL clock start equal.
        service, _ = _service(_owner("consumer-a"))
        created = await _queue(service)
        fresh = await db["downloads"].find_one({"requester": "consumer-a", "s3_key": created.s3_key})
        assert fresh is not None
        assert fresh["original_time"] == fresh["created_at"]

        # After an errored retry, created_at has moved but original_time has not.
        await db["downloads"].update_one(
            {"requester": "consumer-a", "s3_key": created.s3_key},
            {"$set": {"status": JobStatus.error.value, "created_at": datetime.now(UTC) - timedelta(hours=1)}},
        )
        await _queue(service)
        after = await db["downloads"].find_one({"requester": "consumer-a", "s3_key": created.s3_key})
        assert after is not None
        assert after["original_time"] == fresh["original_time"]
        assert after["created_at"] > after["original_time"]

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

    async def test_only_one_of_two_racing_callers_reclaims_errored_ticket(self, db):
        # P4 #15, error branch: sibling to the stale-submitted race, but exercising the
        # ``status == error`` arm of ``claim_for_retry``. Two callers race to reclaim one errored
        # ticket (within the max-retry age); the atomic status flip lets exactly one match, so the
        # loser gets ``None`` back and does not re-enqueue.
        seed, _ = _service(_owner("consumer-a"))
        created = await _queue(seed)
        await db["downloads"].update_one(
            {"requester": "consumer-a", "s3_key": created.s3_key},
            {"$set": {"status": JobStatus.error.value, "error": "boom"}},
        )

        service_a, sqs_a = _service(_owner("consumer-a"))
        service_b, sqs_b = _service(_owner("consumer-a"))
        await asyncio.gather(_queue(service_a), _queue(service_b))

        assert sqs_a.send_message.await_count + sqs_b.send_message.await_count == 1  # one reclaim only
        assert await db["downloads"].count_documents({}) == 1
        stored = await db["downloads"].find_one({"requester": "consumer-a", "s3_key": created.s3_key})
        assert stored is not None
        assert stored["status"] == JobStatus.submitted.value  # flipped back for the worker
        assert stored.get("error") is None  # prior failure cleared by the reclaim


class TestStaleSubmittedReclaim:
    """#10: a job stuck in ``submitted`` (dead worker / lost message) self-heals on re-request,
    but a fresh ``submitted`` job (a worker plausibly still running it) is left alone."""

    async def test_stale_submitted_is_reclaimed_and_re_enqueued(self, db):
        service, sqs = _service(_owner("consumer-a"))
        created = await _queue(service)
        assert sqs.send_message.await_count == 1

        # Presumed-dead worker: the ticket has sat in ``submitted`` well past the staleness window.
        await db["downloads"].update_one(
            {"requester": "consumer-a", "s3_key": created.s3_key},
            {"$set": {"created_at": datetime.now(UTC) - timedelta(hours=1)}},
        )
        before = await db["downloads"].find_one({"requester": "consumer-a", "s3_key": created.s3_key})
        assert before is not None

        reclaimed = await _queue(service)

        assert reclaimed.status == JobStatus.submitted
        assert sqs.send_message.await_count == 2  # re-enqueued
        assert await db["downloads"].count_documents({}) == 1  # still one ticket
        stored = await db["downloads"].find_one({"requester": "consumer-a", "s3_key": created.s3_key})
        assert stored is not None
        assert stored["created_at"] > before["created_at"]  # clock bumped

    async def test_fresh_submitted_is_left_alone(self, db):
        # A just-created ``submitted`` ticket (recent created_at) is a worker still plausibly running
        # it: re-request returns it unchanged and does not re-enqueue.
        service, sqs = _service(_owner("consumer-a"))
        created = await _queue(service)
        assert sqs.send_message.await_count == 1

        again = await _queue(service)

        assert again.status == JobStatus.submitted
        assert again.id == created.id
        assert sqs.send_message.await_count == 1  # unchanged: still in flight

    async def test_only_one_of_two_racing_callers_reclaims(self, db):
        # Dedup under contention (P4 #15): two callers race to reclaim one stale ``submitted`` ticket;
        # the atomic created_at bump lets exactly one win, so the job is enqueued only once more.
        seed, _ = _service(_owner("consumer-a"))
        created = await _queue(seed)
        await db["downloads"].update_one(
            {"requester": "consumer-a", "s3_key": created.s3_key},
            {"$set": {"created_at": datetime.now(UTC) - timedelta(hours=1)}},
        )

        service_a, sqs_a = _service(_owner("consumer-a"))
        service_b, sqs_b = _service(_owner("consumer-a"))
        await asyncio.gather(_queue(service_a), _queue(service_b))

        assert sqs_a.send_message.await_count + sqs_b.send_message.await_count == 1
        assert await db["downloads"].count_documents({}) == 1


class TestMaxRetryAge:
    """The age cap refuses to keep retrying a perpetually-failing ticket, measured on the immutable
    ``original_time`` so a bumped ``created_at`` can't hide the true age. It must not fire on an
    in-flight fresh ``submitted`` ticket."""

    async def test_errored_ticket_past_max_age_is_refused(self, db):
        service, sqs = _service(_owner("consumer-a"))
        created = await _queue(service)
        assert sqs.send_message.await_count == 1

        # Errored, and failing since longer ago than the default 1-day cap.
        await db["downloads"].update_one(
            {"requester": "consumer-a", "s3_key": created.s3_key},
            {
                "$set": {
                    "status": JobStatus.error.value,
                    "error": "boom",
                    "original_time": datetime.now(UTC) - timedelta(days=2),
                }
            },
        )

        with pytest.raises(DownloadRetryExhaustedError):
            await _queue(service)

        assert sqs.send_message.await_count == 1  # not re-enqueued
        stored = await db["downloads"].find_one({"requester": "consumer-a", "s3_key": created.s3_key})
        assert stored is not None
        assert stored["status"] == JobStatus.error.value  # left as-is, not flipped to submitted

    async def test_errored_ticket_within_max_age_still_retries(self, db):
        # Boundary: an errored ticket whose original_time is inside the cap still re-enqueues.
        service, sqs = _service(_owner("consumer-a"))
        created = await _queue(service)
        await db["downloads"].update_one(
            {"requester": "consumer-a", "s3_key": created.s3_key},
            {
                "$set": {
                    "status": JobStatus.error.value,
                    "original_time": datetime.now(UTC) - timedelta(hours=12),
                    "created_at": datetime.now(UTC) - timedelta(hours=12),
                }
            },
        )

        retried = await _queue(service)

        assert retried.status == JobStatus.submitted
        assert sqs.send_message.await_count == 2

    async def test_fresh_in_flight_submitted_is_not_refused(self, db):
        # A worker still running the job looks ``submitted`` with a recent created_at even if the
        # ticket was first submitted long ago: the age cap must not deny the in-progress download.
        service, sqs = _service(_owner("consumer-a"))
        created = await _queue(service)
        await db["downloads"].update_one(
            {"requester": "consumer-a", "s3_key": created.s3_key},
            {"$set": {"original_time": datetime.now(UTC) - timedelta(days=2)}},  # old birth, fresh clock
        )

        again = await _queue(service)  # must not raise

        assert again.status == JobStatus.submitted
        assert sqs.send_message.await_count == 1  # not re-enqueued (still in flight)


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
