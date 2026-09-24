"""End-to-end reachability gating for component reads and queued downloads.

Components (structures/tables/attachments) carry no access field of their own. Visibility is
gated by whether a contribution the caller can see references the component. These tests drive the
real ComponentService against MongoDB to confirm reads only surface reachable components, and that a
queued download embeds the reachable ids in the query the worker will run.
"""

from unittest.mock import AsyncMock

import pytest
from beanie import PydanticObjectId

from mpcontribs_api.authz import User
from mpcontribs_api.domains._shared.service import ComponentService
from mpcontribs_api.domains._shared.types import DownloadFormat
from mpcontribs_api.domains.attachments.models import Attachment, AttachmentFilter
from mpcontribs_api.domains.attachments.repository import MongoDbAttachmentRepository
from mpcontribs_api.domains.contributions.models import Contribution
from mpcontribs_api.domains.contributions.repository import MongoDbContributionRepository
from mpcontribs_api.pagination import CursorParams

pytestmark = [pytest.mark.db, pytest.mark.asyncio(loop_scope="session")]

ANON = User()
# Downloads are authenticated-only, but reachability is a *data*-scope question: an authenticated
# user with no project grants sees exactly the public data an anonymous reader would, so this caller
# exercises the public-only reachability path for the (auth-gated) download tests.
PUBLIC_ONLY = User(username="viewer@example.com")


def _service(user: User) -> ComponentService:
    # ``downloads`` is an AsyncMock so a queued download can be inspected via ``service._downloads``
    # without exercising the DownloadService lifecycle (covered by test_download_queue.py).
    return ComponentService(
        MongoDbAttachmentRepository(user),
        MongoDbContributionRepository(user),
        user=user,
        downloads=AsyncMock(),
        ref_field="attachments",
    )


async def _attachment(content: int) -> Attachment:
    # md5 is server-computed from (mime, content); distinct content -> distinct md5/dedup.
    doc = Attachment(_id=PydanticObjectId(), name="d.csv", mime="application/gzip", content=content)
    await doc.insert()
    return doc


async def _contribution(identifier: str, *, is_public: bool, attachments: list[Attachment]) -> Contribution:
    doc = Contribution(
        _id=PydanticObjectId(),
        project="reach-proj",
        material_id=identifier,
        chemical_system_id="Fe-O",
        formula="Fe2O3",
        data={"x": 1},
        is_public=is_public,
        attachments=attachments,
    )
    await doc.insert()
    return doc


class TestComponentReadReachability:
    async def test_get_by_id_returns_reachable_component(self, db):
        att = await _attachment(1)
        await _contribution("mp-pub", is_public=True, attachments=[att])
        result = await _service(ANON).read_one({"id": str(att.id)}, fields=None)
        assert result is not None
        assert result.id == att.id

    async def test_get_by_id_hides_unreachable_component(self, db):
        att = await _attachment(2)
        # Referenced only by a private contribution -> anonymous cannot reach it.
        await _contribution("mp-priv", is_public=False, attachments=[att])
        result = await _service(ANON).read_one({"id": str(att.id)}, fields=None)
        assert result is None

    async def test_get_by_id_hides_orphan_component(self, db):
        # No contribution references this attachment at all.
        att = await _attachment(3)
        result = await _service(ANON).read_one({"id": str(att.id)}, fields=None)
        assert result is None

    async def test_get_many_only_lists_reachable(self, db):
        pub = await _attachment(10)
        priv = await _attachment(20)
        orphan = await _attachment(30)
        await _contribution("mp-a", is_public=True, attachments=[pub])
        await _contribution("mp-b", is_public=False, attachments=[priv])

        page = await _service(ANON).read_many(filter=AttachmentFilter(), pagination=CursorParams(), fields=None)
        ids = {item.id for item in page.items}

        assert pub.id in ids
        assert priv.id not in ids
        assert orphan.id not in ids


class TestComponentQueueDownloadReachability:
    """A queued component download folds the caller's reachable ids into the query the worker runs,
    so the async export is gated exactly as a synchronous read would be."""

    async def test_queued_query_embeds_only_reachable_ids(self, db):
        pub = await _attachment(1)
        priv = await _attachment(2)
        orphan = await _attachment(3)  # referenced by nothing
        await _contribution("mp-a", is_public=True, attachments=[pub])
        await _contribution("mp-b", is_public=False, attachments=[priv])

        service = _service(PUBLIC_ONLY)
        await service.queue_download(filter=AttachmentFilter(), format=DownloadFormat.CSV)

        call = service._downloads.queue_download.await_args.kwargs
        # The collection is now encoded as the query map key (``domain`` was removed).
        assert set(call["query"]) == {"attachments"}
        assert call["fmt"] == DownloadFormat.CSV
        # The reachability gate lives in the query's `_id $in` clause.
        allowed = call["query"]["attachments"][0]["$and"][1]["_id"]["$in"]
        assert pub.id in allowed  # reachable via a public contribution
        assert priv.id not in allowed  # only a private contribution references it
        assert orphan.id not in allowed  # referenced by no contribution

    async def test_admin_reaches_private_and_public(self, db):
        admin = User(username="google:admin@example.com", groups=frozenset({"admin"}))
        pub = await _attachment(10)
        priv = await _attachment(20)
        await _contribution("mp-a", is_public=True, attachments=[pub])
        await _contribution("mp-b", is_public=False, attachments=[priv])

        service = _service(admin)
        await service.queue_download(filter=AttachmentFilter(), format=DownloadFormat.JSONL)

        allowed = service._downloads.queue_download.await_args.kwargs["query"]["attachments"][0]["$and"][1]["_id"]["$in"]
        assert pub.id in allowed and priv.id in allowed  # admin bypasses scope

    async def test_no_reachable_components_queues_empty_allow_list(self, db):
        # A public-only caller can reach nothing referenced only by a private contribution: the query
        # carries an empty `_id $in []`, i.e. an empty export rather than the whole collection.
        att = await _attachment(30)
        await _contribution("mp-x", is_public=False, attachments=[att])

        service = _service(PUBLIC_ONLY)
        await service.queue_download(filter=AttachmentFilter(), format=DownloadFormat.JSONL)

        allowed = service._downloads.queue_download.await_args.kwargs["query"]["attachments"][0]["$and"][1]["_id"]["$in"]
        assert allowed == []

    async def test_caller_id_filter_is_preserved_alongside_scope_clause(self, db):
        # P4 #17: a non-empty caller filter must survive as its own `$and` clause rather than being
        # overwritten by the reachability `_id $in`. Two attachments are reachable, but the caller
        # asks for only one by id; the queued query must carry *both* clauses so the worker runs
        # their intersection (every reachability test elsewhere uses an empty filter, so this is the
        # only place a real caller `_id` clause is verified to coexist with the scope clause).
        pub = await _attachment(1)
        extra = await _attachment(2)
        await _contribution("mp-a", is_public=True, attachments=[pub, extra])

        service = _service(PUBLIC_ONLY)
        await service.queue_download(filter=AttachmentFilter(id__in=[pub.id]), format=DownloadFormat.JSONL)

        query = service._downloads.queue_download.await_args.kwargs["query"]
        base_clause, scope_clause = query["attachments"][0]["$and"]
        # The caller's id__in survives as its own clause inside the base query (which beanie wraps as
        # `{"$and": [<empty component scope>, <caller filter>]}`)...
        assert {"_id": {"$in": [pub.id]}} in base_clause["$and"]
        # ...and the reachability allow-list is a *separate* top-level clause carrying every reachable
        # id (both), sorted for a stable s3_key. Their $and is the intersection, effectively just `pub`.
        assert scope_clause == {"_id": {"$in": sorted([pub.id, extra.id])}}

    async def test_queued_ids_are_sorted_for_a_stable_s3_key(self, db):
        # ``referenced_component_ids`` returns an unordered set; embedding it unsorted would make the
        # hashed s3_key non-deterministic across processes and silently defeat download dedup. The
        # query must carry the ids in a deterministic (sorted) order.
        atts = [await _attachment(i) for i in range(40, 48)]
        await _contribution("mp-sorted", is_public=True, attachments=atts)

        service = _service(PUBLIC_ONLY)
        await service.queue_download(filter=AttachmentFilter(), format=DownloadFormat.JSONL)

        allowed = service._downloads.queue_download.await_args.kwargs["query"]["attachments"][0]["$and"][1]["_id"]["$in"]
        assert len(allowed) == len(atts)
        # ``build_s3_key`` hashes the id list as-is (canonicalization sorts dict keys, not list
        # elements), so a deterministic key depends on the ids being sorted here at the source.
        assert allowed == sorted(allowed)
