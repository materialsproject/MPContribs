import gzip
from unittest.mock import MagicMock

import pytest
from beanie import PydanticObjectId

from mpcontribs_api.authz import User
from mpcontribs_api.config import get_settings
from mpcontribs_api.domains._shared.types import DownloadFormat, ShortMimeFormat
from mpcontribs_api.domains.attachments.models import (
    Attachment,
    AttachmentFilter,
    AttachmentIn,
    AttachmentPatch,
)
from mpcontribs_api.domains.attachments.repository import MongoDbAttachmentRepository

pytestmark = [pytest.mark.db, pytest.mark.asyncio(loop_scope="session")]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

USER = User(username="google:alice@example.com", groups=frozenset({"mp-team"}))


def _repo() -> MongoDbAttachmentRepository:
    return MongoDbAttachmentRepository(USER)


def _attachment(md5: str, name: str = "data.csv", content: int = 1) -> AttachmentIn:
    return AttachmentIn(
        _id=PydanticObjectId(),
        name=name,
        md5=md5,
        mime="application/gzip",
        content=content,
    )


async def _count() -> int:
    return await Attachment.find_all().count()


# ---------------------------------------------------------------------------
# insert_components: md5 dedupe
# ---------------------------------------------------------------------------


class TestInsertComponentsDedupe:
    async def test_duplicate_md5_in_batch_inserted_once(self, db):
        # Two inputs share an md5; only one document should be written.
        await _repo().insert_components([_attachment("a" * 32), _attachment("a" * 32), _attachment("b" * 32)])
        assert await _count() == 2

    async def test_returns_one_doc_per_unique_md5(self, db):
        result = await _repo().insert_components([_attachment("a" * 32), _attachment("a" * 32)])
        assert len(result) == 1

    async def test_existing_md5_not_reinserted(self, db):
        await _repo().insert_components([_attachment("a" * 32)])
        # Re-submit the existing md5 alongside a new one.
        await _repo().insert_components([_attachment("a" * 32), _attachment("b" * 32)])
        assert await _count() == 2

    async def test_existing_doc_returned_with_original_id(self, db):
        first = await _repo().insert_components([_attachment("a" * 32)])
        again = await _repo().insert_components([_attachment("a" * 32)])
        assert again[0].id == first[0].id

    async def test_inserted_docs_have_ids(self, db):
        result = await _repo().insert_components([_attachment("a" * 32), _attachment("b" * 32)])
        assert all(doc.id is not None for doc in result)


# ---------------------------------------------------------------------------
# insert_components: chunking
# ---------------------------------------------------------------------------


class TestInsertComponentsChunking:
    async def test_all_docs_persisted_across_multiple_chunks(self, db, monkeypatch):
        # Force a chunk size smaller than the batch so the chunking loop runs >1 time.
        monkeypatch.setattr(get_settings().mongo, "component_insert_chunk_size", 2)
        # md5 must be 32-char hex; build distinct values explicitly.
        attachments = [_attachment(format(i, "032x")) for i in range(5)]
        result = await _repo().insert_components(attachments)
        assert len(result) == 5
        assert await _count() == 5


# ---------------------------------------------------------------------------
# insert_component (single)
# ---------------------------------------------------------------------------


class TestInsertComponent:
    async def test_single_insert_persists(self, db):
        doc = await _repo().insert_component(_attachment("c" * 32))
        found = await Attachment.find_one(Attachment.id == doc.id)
        assert found is not None
        assert found.md5 == "c" * 32


# ---------------------------------------------------------------------------
# delete_components / delete_component_by_id
# ---------------------------------------------------------------------------


class TestDeleteComponents:
    async def test_filtered_delete_removes_only_matches(self, db):
        await _repo().insert_components([_attachment("a" * 32), _attachment("b" * 32)])
        result = await _repo().delete_components(AttachmentFilter(md5="a" * 32))
        assert result.num_deleted == 1
        remaining = {doc.md5 async for doc in Attachment.find_all()}
        assert remaining == {"b" * 32}

    async def test_delete_by_id_removes_one(self, db):
        """delete_component_by_id matches a string id by converting it to ObjectId."""
        [doc] = await _repo().insert_components([_attachment("a" * 32)])
        result = await _repo().delete_component_by_id(str(doc.id))
        assert result.num_deleted == 1
        assert await _count() == 0

    async def test_delete_by_unknown_id_raises(self, db):
        from mpcontribs_api.exceptions import NotFoundError

        with pytest.raises(NotFoundError):
            await _repo().delete_component_by_id(str(PydanticObjectId()))


# ---------------------------------------------------------------------------
# patch_component_by_id
# ---------------------------------------------------------------------------


class TestPatchComponent:
    async def test_patch_updates_field(self, db):
        [doc] = await _repo().insert_components([_attachment("a" * 32, name="data.csv")])
        updated = await _repo().patch_component_by_id(str(doc.id), AttachmentPatch(name="renamed.png"))
        assert updated.name == "renamed.png"

    async def test_empty_patch_returns_existing(self, db):
        [doc] = await _repo().insert_components([_attachment("a" * 32, name="data.csv")])
        updated = await _repo().patch_component_by_id(str(doc.id), AttachmentPatch())
        assert updated.id == doc.id


# ---------------------------------------------------------------------------
# Component download round-trip
# ---------------------------------------------------------------------------


class TestComponentDownload:
    async def test_jsonl_download_round_trips(self, db):
        """Component downloads stream a decompressable gzip of all rows."""
        await _repo().insert_components([_attachment("a" * 32), _attachment("b" * 32)])
        stream = await _repo().download_attachments(
            format=DownloadFormat.JSONL,
            short_mime=ShortMimeFormat.GZ,
            ignore_cache=True,
            filter=AttachmentFilter(),
            fields=None,
            s3=MagicMock(),
        )
        chunks = [c async for c in stream]
        decompressed = gzip.decompress(b"".join(chunks))
        assert decompressed.count(b"\n") == 2
