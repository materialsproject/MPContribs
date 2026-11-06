"""Integration tests for the thin, content-addressed component repository (real MongoDB).

Components are worker-written now — the API never inserts or patches them — so these tests seed the
collection directly (simulating the worker) and exercise the repository surface that survives: reads by
id and by the ``(project, hash)`` natural key, filtered reads, and the ``delete_many``/``delete_one``
the contribution cascade relies on. The repository applies no scope of its own (``read_scope`` is
empty); access is gated above it in :class:`ComponentService` by contribution/project reachability.
"""

import pytest
from beanie import PydanticObjectId

from mpcontribs_api.authz import User
from mpcontribs_api.domains.attachments.models import Attachment, AttachmentFilter
from mpcontribs_api.domains.attachments.repository import MongoDbAttachmentRepository
from mpcontribs_api.exceptions import NotFoundError

pytestmark = [pytest.mark.db, pytest.mark.asyncio(loop_scope="session")]

USER = User(username="google:alice@example.com", groups=frozenset({"mp-team"}))

HASH_A = "a" * 64
HASH_B = "b" * 64


def _repo() -> MongoDbAttachmentRepository:
    return MongoDbAttachmentRepository(USER)


def _attachment(hash: str = HASH_A, *, project: str = "my_project", size: int = 1024) -> Attachment:
    """Build a worker-style attachment locator (no API write path exists for components)."""
    return Attachment.model_validate(
        {"_id": PydanticObjectId(), "project": project, "hash": hash, "size": size, "ext": "png", "mime": "image/png"}
    )


async def _seed(*docs: Attachment) -> list[Attachment]:
    await Attachment.insert_many(list(docs))
    return list(docs)


async def _count() -> int:
    return await Attachment.find_all().count()


class TestReadComponent:
    async def test_read_one_by_id(self, db):
        [doc] = await _seed(_attachment())
        found = await _repo().read_one({"id": doc.id}, fields=None)
        assert found is not None
        assert found.id == doc.id
        assert found.hash == HASH_A

    async def test_read_one_by_project_and_hash(self, db):
        [doc] = await _seed(_attachment())
        by_key = await _repo().read_one({"project": "my_project", "hash": HASH_A}, fields=None)
        assert by_key is not None
        assert by_key.id == doc.id

    async def test_read_one_missing_returns_none(self, db):
        assert await _repo().read_one({"id": PydanticObjectId()}, fields=None) is None

    async def test_read_many_filters_by_hash(self, db):
        keep, _ = await _seed(_attachment(HASH_A), _attachment(HASH_B))
        page = await _repo().read_many(filter=AttachmentFilter(hash=HASH_A), fields=None)
        assert [item.id for item in page.items] == [keep.id]


class TestDeleteComponent:
    async def test_delete_many_removes_only_matches(self, db):
        keep, drop = await _seed(_attachment(HASH_A), _attachment(HASH_B))
        result = await _repo().delete_many(AttachmentFilter(hash=HASH_B))
        assert result.num_deleted == 1
        remaining = {doc.hash async for doc in Attachment.find_all()}
        assert remaining == {keep.hash}

    async def test_delete_many_by_id_in_supports_cascade(self, db):
        # The contribution cascade deletes a component set by id__in; mirror that call shape.
        a, b = await _seed(_attachment(HASH_A), _attachment(HASH_B))
        result = await _repo().delete_many(AttachmentFilter(id__in=[a.id, b.id]))
        assert result.num_deleted == 2
        assert await _count() == 0

    async def test_delete_one_by_id(self, db):
        [doc] = await _seed(_attachment())
        result = await _repo().delete_one({"id": doc.id})
        assert result.num_deleted == 1
        assert await _count() == 0

    async def test_delete_one_by_project_and_hash(self, db):
        [doc] = await _seed(_attachment())
        result = await _repo().delete_one({"project": "my_project", "hash": HASH_A})
        assert result.num_deleted == 1
        assert await _count() == 0

    async def test_delete_one_unknown_id_raises(self, db):
        with pytest.raises(NotFoundError):
            await _repo().delete_one({"id": PydanticObjectId()})
