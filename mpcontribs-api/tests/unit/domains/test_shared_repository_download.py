import csv
import gzip
import io
import json
from collections.abc import AsyncIterable, AsyncIterator
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from beanie import PydanticObjectId
from pydantic import BaseModel

from mpcontribs_api.authz import User
from mpcontribs_api.domains._shared.repository import MongoDbRepository
from mpcontribs_api.domains._shared.types import DownloadFormat, ShortMimeFormat

# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _Out(BaseModel):
    """Minimal output model with scalar fields."""

    a: int
    b: str


class _OutWithData(BaseModel):
    """Output model whose ``data`` column holds a nested dict (CSV edge case)."""

    name: str
    data: dict


class _FakeQuery:
    """Async-iterable stand-in for a Beanie find() query."""

    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    async def __aiter__(self) -> AsyncIterator[Any]:
        for row in self._rows:
            yield row


class _FakeFilter:
    """Stand-in for a fastapi-filter Filter.

    ``filter()`` ignores the base query and returns a fake query over the seeded
    rows; ``sort()`` is a passthrough; ``model_dump()`` returns the configured
    payload (used by ``download`` when building the cache key).
    """

    def __init__(self, rows: list[Any], dump: dict[str, Any] | None = None) -> None:
        self._rows = rows
        self._dump = {} if dump is None else dump

    def filter(self, _base: Any) -> _FakeQuery:
        return _FakeQuery(self._rows)

    def sort(self, query: _FakeQuery) -> _FakeQuery:
        return query

    def model_dump(self) -> dict[str, Any]:
        return self._dump


class _FakeRepo(MongoDbRepository):
    """Concrete repository binding just enough to exercise the shared download core."""

    document_model = MagicMock()
    out_model = _Out

    @staticmethod
    def _build_scope(user: User) -> dict[str, Any]:
        return {}


def _repo(out_model: type[BaseModel] = _Out) -> _FakeRepo:
    repo = _FakeRepo(User())
    repo.out_model = out_model  # type: ignore[assignment]
    repo.document_model = MagicMock()  # type: ignore[assignment]
    return repo


async def _aiter(items: list[Any]) -> AsyncIterator[Any]:
    for item in items:
        yield item


async def _collect(stream: AsyncIterable[bytes]) -> bytes:
    chunks: list[bytes] = []
    async for chunk in stream:
        chunks.append(chunk)
    return b"".join(chunks)


# ===========================================================================
# _serialize_jsonl
# ===========================================================================


class TestSerializeJsonl:
    async def test_one_line_per_row(self):
        rows = [_Out(a=1, b="x"), _Out(a=2, b="y")]
        out = await _collect(MongoDbRepository._serialize_jsonl(_aiter(rows)))
        assert out.count(b"\n") == 2

    async def test_each_line_round_trips_to_row(self):
        rows = [_Out(a=1, b="x"), _Out(a=2, b="y")]
        out = await _collect(MongoDbRepository._serialize_jsonl(_aiter(rows)))
        parsed = [json.loads(line) for line in out.splitlines()]
        assert parsed == [{"a": 1, "b": "x"}, {"a": 2, "b": "y"}]

    async def test_every_line_terminated_with_newline(self):
        rows = [_Out(a=1, b="x"), _Out(a=2, b="y")]
        out = await _collect(MongoDbRepository._serialize_jsonl(_aiter(rows)))
        assert out.endswith(b"\n")

    async def test_empty_input_yields_nothing(self):
        out = await _collect(MongoDbRepository._serialize_jsonl(_aiter([])))
        assert out == b""

    async def test_unicode_payload_preserved(self):
        rows = [_Out(a=1, b="café—ü")]
        out = await _collect(MongoDbRepository._serialize_jsonl(_aiter(rows)))
        assert json.loads(out)["b"] == "café—ü"


# ===========================================================================
# _serialize_csv
# ===========================================================================


def _parse_csv(raw: bytes) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(raw.decode())))


class TestSerializeCsv:
    async def test_header_written_once(self):
        rows = [_Out(a=1, b="x"), _Out(a=2, b="y")]
        raw = await _collect(MongoDbRepository._serialize_csv(_aiter(rows), None))
        # Header appears exactly once even across multiple rows.
        assert raw.decode().count("a,b") == 1

    async def test_columns_default_to_first_row_keys_when_no_fields(self):
        rows = [_Out(a=1, b="x")]
        raw = await _collect(MongoDbRepository._serialize_csv(_aiter(rows), None))
        reader = csv.reader(io.StringIO(raw.decode()))
        assert next(reader) == ["a", "b"]

    async def test_columns_follow_sorted_fields_when_given(self):
        rows = [_Out(a=1, b="x")]
        raw = await _collect(MongoDbRepository._serialize_csv(_aiter(rows), frozenset({"b", "a"})))
        reader = csv.reader(io.StringIO(raw.decode()))
        assert next(reader) == ["a", "b"]

    async def test_extra_fields_are_ignored(self):
        # 'b' is not in the requested field set -> dropped from output.
        rows = [_Out(a=1, b="x")]
        raw = await _collect(MongoDbRepository._serialize_csv(_aiter(rows), frozenset({"a"})))
        parsed = _parse_csv(raw)
        assert parsed == [{"a": "1"}]

    async def test_all_rows_emitted(self):
        rows = [_Out(a=i, b=str(i)) for i in range(5)]
        raw = await _collect(MongoDbRepository._serialize_csv(_aiter(rows), None))
        assert len(_parse_csv(raw)) == 5

    async def test_no_row_bleed_between_chunks(self):
        # Each yielded chunk after the header must contain exactly one row, proving
        # the shared StringIO buffer is truncated between iterations.
        rows = [_Out(a=1, b="x"), _Out(a=2, b="y")]
        chunks = [c async for c in MongoDbRepository._serialize_csv(_aiter(rows), None)]
        # First chunk: header + row 1; subsequent chunks: one row each.
        assert b"2,y" not in chunks[0]

    async def test_empty_input_yields_no_bytes(self):
        raw = await _collect(MongoDbRepository._serialize_csv(_aiter([]), None))
        assert raw == b""

    async def test_dict_value_serialized_as_json(self):
        """Dict-valued columns are emitted as JSON, not Python repr.

        ``model_dump(mode="json")`` leaves nested dicts as dict objects; the serializer
        JSON-encodes them so the cell is valid JSON a consumer can round-trip (rather
        than ``str(dict)``, the single-quoted Python repr).
        """
        rows = [_OutWithData(name="r1", data={"k": "v", "n": 1})]
        raw = await _collect(MongoDbRepository._serialize_csv(_aiter(rows), None))
        cell = _parse_csv(raw)[0]["data"]
        assert json.loads(cell) == {"k": "v", "n": 1}


# ===========================================================================
# _get_serializer
# ===========================================================================


class TestGetSerializer:
    @pytest.mark.parametrize("format", list(DownloadFormat))
    async def test_every_format_dispatches_to_a_usable_serializer(self, format: DownloadFormat):
        """Every ``DownloadFormat`` member maps to a serializer of the expected shape.

        ``_get_serializer`` has no default case, so an unhandled member would silently
        return ``None``. Parametrizing over every member guarantees the match stays
        exhaustive: adding a format without a matching case fails here rather than at
        request time. The returned object is uniformly a callable taking the row stream
        and yielding ``bytes``, regardless of which format produced it.
        """
        repo = _repo()
        serializer = repo._get_serializer(format, None)
        assert callable(serializer)
        raw = await _collect(serializer(_aiter([_Out(a=1, b="x")])))
        assert isinstance(raw, bytes) and raw

    async def test_jsonl_dispatches_to_jsonl_output(self):
        repo = _repo()
        serializer = repo._get_serializer(DownloadFormat.JSONL, None)
        raw = await _collect(serializer(_aiter([_Out(a=1, b="x")])))
        assert json.loads(raw) == {"a": 1, "b": "x"}

    async def test_csv_dispatches_to_csv_output_and_threads_fields(self):
        # The fields passed to _get_serializer must reach the CSV serializer: 'b' is
        # dropped because only 'a' was requested.
        repo = _repo()
        serializer = repo._get_serializer(DownloadFormat.CSV, frozenset({"a"}))
        raw = await _collect(serializer(_aiter([_Out(a=1, b="x")])))
        assert _parse_csv(raw) == [{"a": "1"}]


# ===========================================================================
# _hash_payload
# ===========================================================================


class TestHashPayload:
    def test_is_deterministic(self):
        repo = _repo()
        payload = {"format": "jsonl", "fields": ["a", "b"]}
        assert repo._hash_payload(payload) == repo._hash_payload(payload)

    def test_independent_of_key_order(self):
        repo = _repo()
        assert repo._hash_payload({"a": 1, "b": 2}) == repo._hash_payload({"b": 2, "a": 1})

    def test_sensitive_to_value_changes(self):
        repo = _repo()
        assert repo._hash_payload({"a": 1}) != repo._hash_payload({"a": 2})

    def test_returns_sha256_hex(self):
        repo = _repo()
        digest = repo._hash_payload({"a": 1})
        assert len(digest) == 64
        assert all(c in "0123456789abcdef" for c in digest)

    def test_object_id_filter_is_hashable(self):
        """Filters carrying an ObjectId hash without raising.

        ``download`` hashes ``filter.model_dump()`` which, for an ``id__in`` filter,
        contains PydanticObjectId values.  ``_hash_payload`` passes ``default=str`` so
        these stringify into a stable key instead of raising ``TypeError``.
        """
        repo = _repo()
        payload = {"filter": {"id__in": [PydanticObjectId(), PydanticObjectId()]}}
        digest = repo._hash_payload(payload)
        assert len(digest) == 64

    def test_datetime_filter_is_hashable(self):
        """Filters carrying a datetime hash without raising (see above)."""
        repo = _repo()
        payload = {"filter": {"created__gte": datetime(2024, 1, 1, tzinfo=timezone.utc)}}
        digest = repo._hash_payload(payload)
        assert len(digest) == 64


# ===========================================================================
# download (end-to-end: query -> serialize -> gzip stream)
# ===========================================================================


class TestDownload:
    async def test_jsonl_stream_decompresses_to_rows(self):
        """The gzip stream decompresses cleanly to the JSONL payload.

        ``download`` flushes the zlib gzip compressor after the final chunk so the
        trailing buffered bytes and the gzip footer (CRC32 + ISIZE) are emitted.
        Regression guard: without the flush the member is truncated and
        ``gzip.decompress`` raises.
        """
        repo = _repo(_Out)
        filter = _FakeFilter(rows=[SimpleNamespace(a=1, b="x"), SimpleNamespace(a=2, b="y")])
        stream = repo.download(
            format=DownloadFormat.JSONL,
            short_mime=ShortMimeFormat.GZ,
            ignore_cache=True,
            filter=filter,  # type: ignore[arg-type]
            fields=None,
            s3=MagicMock(),
            bucket_name="test-bucket",
            key_name="test-key",
        )
        compressed = await _collect(stream)
        decompressed = gzip.decompress(compressed)
        parsed = [json.loads(line) for line in decompressed.splitlines()]
        assert parsed == [{"a": 1, "b": "x"}, {"a": 2, "b": "y"}]

    async def test_csv_stream_decompresses_to_rows(self):
        """Same gzip flush guard, exercised through the CSV serializer."""
        repo = _repo(_Out)
        filter = _FakeFilter(rows=[SimpleNamespace(a=1, b="x"), SimpleNamespace(a=2, b="y")])
        stream = repo.download(
            format=DownloadFormat.CSV,
            short_mime=ShortMimeFormat.GZ,
            ignore_cache=True,
            filter=filter,  # type: ignore[arg-type]
            fields=frozenset({"a", "b"}),
            s3=MagicMock(),
            bucket_name="test-bucket",
            key_name="test-key",
        )
        compressed = await _collect(stream)
        decompressed = gzip.decompress(compressed)
        assert _parse_csv(decompressed) == [{"a": "1", "b": "x"}, {"a": "2", "b": "y"}]

    async def test_empty_result_is_valid_empty_gzip(self):
        """A download with no matching rows yields zero bytes, which gzip treats as empty.

        Unlike the non-empty cases (which hit the missing-``flush()`` bug), an empty
        result never enters the compress loop, so the stream is genuinely empty and
        ``gzip.decompress(b"")`` returns ``b""``.  Guards that empty downloads stay valid.
        """
        repo = _repo(_Out)
        filter = _FakeFilter(rows=[])
        stream = repo.download(
            format=DownloadFormat.JSONL,
            short_mime=ShortMimeFormat.GZ,
            ignore_cache=True,
            filter=filter,  # type: ignore[arg-type]
            fields=None,
            s3=MagicMock(),
            bucket_name="test-bucket",
            key_name="test-key",
        )
        compressed = await _collect(stream)
        assert gzip.decompress(compressed) == b""
