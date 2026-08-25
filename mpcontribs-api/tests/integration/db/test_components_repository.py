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


def _attachment(content: int = 1, name: str = "data.csv") -> AttachmentIn:
    # md5 is server-computed from (mime, content), so `content` drives dedup identity.
    return AttachmentIn(name=name, mime="application/gzip", content=content)


async def _count() -> int:
    return await Attachment.find_all().count()


def _build(repo, inputs) -> list:
    """Coerce inputs into stored documents the way the service layer does before inserting.

    The repository's ``insert_many`` now takes fully-built documents (md5 is computed by the model on
    validation), so tests build via ``from_input`` first.
    """
    return [repo.document_model.from_input(i) for i in inputs]


async def _insert(repo, inputs) -> list:
    """Insert and return just the resolved docs, asserting no per-item failures.

    ``insert_many`` now returns ``(indexed_successes, failures)`` (per-item reporting); most tests
    only care about the resolved documents on the success path.
    """
    successes, failures = await repo.insert_many(_build(repo, inputs))
    assert failures == []
    return [doc for _, doc in successes]


# ---------------------------------------------------------------------------
# insert_many: md5 dedupe
# ---------------------------------------------------------------------------


class TestInsertComponentsDedupe:
    async def test_duplicate_content_in_batch_inserted_once(self, db):
        # Two inputs share content (-> same md5); only one document should be written.
        repo = _repo()
        await repo.insert_many(_build(repo, [_attachment(1), _attachment(1), _attachment(2)]))
        assert await _count() == 2

    async def test_returns_one_doc_per_input_deduped_to_same_doc(self, db):
        docs = await _insert(_repo(), [_attachment(1), _attachment(1)])
        assert len(docs) == 2
        assert docs[0].id == docs[1].id

    async def test_existing_md5_not_reinserted(self, db):
        repo = _repo()
        await repo.insert_many(_build(repo, [_attachment(1)]))
        # Re-submit the existing content alongside new content.
        await repo.insert_many(_build(repo, [_attachment(1), _attachment(2)]))
        assert await _count() == 2

    async def test_existing_doc_returned_with_original_id(self, db):
        first = await _insert(_repo(), [_attachment(1)])
        again = await _insert(_repo(), [_attachment(1)])
        assert again[0].id == first[0].id

    async def test_inserted_docs_have_ids(self, db):
        docs = await _insert(_repo(), [_attachment(1), _attachment(2)])
        assert all(doc.id is not None for doc in docs)


# ---------------------------------------------------------------------------
# insert_many: chunking
# ---------------------------------------------------------------------------


class TestInsertComponentsChunking:
    async def test_all_docs_persisted_across_multiple_chunks(self, db, monkeypatch):
        # Force a chunk size smaller than the batch so the chunking loop runs >1 time.
        monkeypatch.setattr(get_settings().mongo, "component_insert_chunk_size", 2)
        # Distinct content -> distinct md5 so all five survive dedup.
        attachments = [_attachment(i) for i in range(5)]
        docs = await _insert(_repo(), attachments)
        assert len(docs) == 5
        assert await _count() == 5


# ---------------------------------------------------------------------------
# insert_one (single)
# ---------------------------------------------------------------------------


class TestInsertComponent:
    async def test_single_insert_persists(self, db):
        repo = _repo()
        [built] = _build(repo, [_attachment(3)])
        doc = await repo.insert_one(built)
        found = await Attachment.find_one(Attachment.id == doc.id)
        assert found is not None
        assert found.md5 == doc.md5
        assert len(found.md5) == 32


# ---------------------------------------------------------------------------
# delete_many / delete_one
# ---------------------------------------------------------------------------


class TestDeleteComponents:
    async def test_filtered_delete_removes_only_matches(self, db):
        keep, drop = await _insert(_repo(), [_attachment(1), _attachment(2)])
        result = await _repo().delete_many(AttachmentFilter(md5=drop.md5))
        assert result.num_deleted == 1
        remaining = {doc.md5 async for doc in Attachment.find_all()}
        assert remaining == {keep.md5}

    async def test_delete_by_id_removes_one(self, db):
        """The inherited base delete_one removes a single component by its primary key."""
        [doc] = await _insert(_repo(),[_attachment(1)])
        result = await _repo().delete_one({"id": doc.id})
        assert result.num_deleted == 1
        assert await _count() == 0

    async def test_delete_by_unknown_id_raises(self, db):
        from mpcontribs_api.exceptions import NotFoundError

        with pytest.raises(NotFoundError):
            await _repo().delete_one({"id": PydanticObjectId()})

    async def test_delete_by_md5_removes_one(self, db):
        """A component is addressable by its content md5 (its declared identifier) as well as by id."""
        [doc] = await _insert(_repo(),[_attachment(1)])
        result = await _repo().delete_one({"md5": doc.md5})
        assert result.num_deleted == 1
        assert await _count() == 0


# ---------------------------------------------------------------------------
# read_one / update_one address a component by id or by its content md5
# ---------------------------------------------------------------------------


class TestAddressComponentByMd5:
    async def test_get_one_by_md5(self, db):
        [doc] = await _insert(_repo(),[_attachment(1)])
        by_md5 = await _repo().read_one({"md5": doc.md5}, fields=None)
        by_id = await _repo().read_one({"id": doc.id}, fields=None)
        assert by_md5 is not None
        assert by_md5.id == by_id.id == doc.id

    async def test_patch_one_by_md5(self, db):
        [doc] = await _insert(_repo(),[_attachment(1, name="data.csv")])
        updated = await _repo().update_one({"md5": doc.md5}, AttachmentPatch(name="renamed.png"))
        assert updated.name == "renamed.png"


# ---------------------------------------------------------------------------
# update_one recomputes the derived md5
# ---------------------------------------------------------------------------


class TestPatchComponent:
    async def test_patch_updates_field(self, db):
        [doc] = await _insert(_repo(),[_attachment(1, name="data.csv")])
        updated = await _repo().update_one({"id": doc.id}, AttachmentPatch(name="renamed.png"))
        assert updated.name == "renamed.png"

    async def test_empty_patch_returns_existing(self, db):
        [doc] = await _insert(_repo(),[_attachment(1, name="data.csv")])
        updated = await _repo().update_one({"id": doc.id}, AttachmentPatch())
        assert updated.id == doc.id

    async def test_patch_content_recomputes_md5(self, db):
        # name is not a hash field, so renaming must NOT change md5.
        [doc] = await _insert(_repo(),[_attachment(1)])
        renamed = await _repo().update_one({"id": doc.id}, AttachmentPatch(name="renamed.png"))
        assert renamed.md5 == doc.md5
        # content IS a hash field, so changing it must recompute md5.
        rehashed = await _repo().update_one({"id": doc.id}, AttachmentPatch(content=999))
        assert rehashed.md5 != doc.md5
        persisted = await Attachment.find_one(Attachment.id == doc.id)
        assert persisted.md5 == rehashed.md5


# ---------------------------------------------------------------------------
# Component download round-trip
# ---------------------------------------------------------------------------


class TestComponentDownload:
    async def test_jsonl_download_round_trips(self, db):
        """Component downloads stream a decompressable gzip of all rows."""
        repo = _repo()
        await repo.insert_many(_build(repo, [_attachment(1), _attachment(2)]))
        stream = _repo().download(
            format=DownloadFormat.JSONL,
            short_mime=ShortMimeFormat.GZ,
            ignore_cache=True,
            filter=AttachmentFilter(),
            fields=None,
            s3=MagicMock(),
            bucket_name="attachments",
            key_name="",
        )
        chunks = [c async for c in stream]
        decompressed = gzip.decompress(b"".join(chunks))
        assert decompressed.count(b"\n") == 2


# ---------------------------------------------------------------------------
# Table DataFrame <-> stored (index/columns/data) round-trips through Mongo
# ---------------------------------------------------------------------------


class TestTableFrameRoundTrip:
    async def test_table_frame_round_trips_via_storage_shape(self, db):
        import polars as pl

        from mpcontribs_api.authz import User
        from mpcontribs_api.domains.tables.models import TableIn, TableOut
        from mpcontribs_api.domains.tables.repository import MongoDbTableRepository

        repo = MongoDbTableRepository(User(username="x", groups=frozenset()))
        # First column is the index (named "T [K]"); cells stay as the original formatted strings.
        frame = pl.DataFrame(
            {
                "T [K]": ["100.0", "200.0"],
                "1e16": ["2.2718689×10²¹", "2.2745466×10²¹"],
                "1e17": ["2.2718684×10²¹", "2.2745438×10²¹"],
            }
        )
        tin = TableIn(
            name="σ(p)",
            attrs={"title": "g", "labels": {"index": "T [K]", "value": "σ", "variable": "doping"}},
            data=frame,
        )
        [doc] = await _insert(repo, [tin])

        # Stored in the canonical MongoDB shape: index/columns/data as strings.
        raw = await db["tables"].find_one({"_id": doc.id})
        assert raw["index"] == ["100.0", "200.0"]
        assert raw["columns"] == ["1e16", "1e17"]
        assert raw["data"] == [["2.2718689×10²¹", "2.2718684×10²¹"], ["2.2745466×10²¹", "2.2745438×10²¹"]]
        assert raw["total_data_rows"] == 2

        # Read back: reassembled into the same DataFrame (index folded back as the first column).
        out = await repo.read_one({"id": doc.id}, TableOut.parse_fields(["data"]))
        assert out.data.columns == ["T [K]", "1e16", "1e17"]
        assert out.data.equals(frame)
        # The raw storage keys must not leak onto the response model.
        assert "index" not in out.model_dump()
        await db["tables"].delete_many({"_id": doc.id})
