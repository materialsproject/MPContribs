import csv
import io
import json
from collections.abc import AsyncIterable, AsyncIterator
from datetime import UTC, datetime
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from beanie import PydanticObjectId
from pydantic import BaseModel

from mpcontribs_api.authz import User
from mpcontribs_api.domains._shared.downloadable import DownloadableRepository
from mpcontribs_api.domains._shared.repository import MongoDbRepository
from mpcontribs_api.domains._shared.types import DownloadFormat
from mpcontribs_api.exceptions import DownloadError
from mpcontribs_api.scope import Scope

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


class _FakeRepo(DownloadableRepository, MongoDbRepository):
    """A repository that mixes in the download capability, binding just enough to exercise it.

    Mirrors how a real download-capable repository is composed — ``DownloadableRepository`` before
    the base ``MongoDbRepository`` — so the mixin resolves ``document_model`` / ``out_model`` /
    ``_scope`` off the concrete repo exactly as it does in production.
    """

    document_model = MagicMock()
    out_model = _Out
    read_scope = Scope()


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
        out = await _collect(DownloadableRepository._serialize_jsonl(_aiter(rows)))
        assert out.count(b"\n") == 2

    async def test_each_line_round_trips_to_row(self):
        rows = [_Out(a=1, b="x"), _Out(a=2, b="y")]
        out = await _collect(DownloadableRepository._serialize_jsonl(_aiter(rows)))
        parsed = [json.loads(line) for line in out.splitlines()]
        assert parsed == [{"a": 1, "b": "x"}, {"a": 2, "b": "y"}]

    async def test_every_line_terminated_with_newline(self):
        rows = [_Out(a=1, b="x"), _Out(a=2, b="y")]
        out = await _collect(DownloadableRepository._serialize_jsonl(_aiter(rows)))
        assert out.endswith(b"\n")

    async def test_empty_input_yields_nothing(self):
        out = await _collect(DownloadableRepository._serialize_jsonl(_aiter([])))
        assert out == b""

    async def test_unicode_payload_preserved(self):
        rows = [_Out(a=1, b="café—ü")]
        out = await _collect(DownloadableRepository._serialize_jsonl(_aiter(rows)))
        assert json.loads(out)["b"] == "café—ü"


# ===========================================================================
# _serialize_csv
# ===========================================================================


def _parse_csv(raw: bytes) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(raw.decode())))


class TestSerializeCsv:
    async def test_header_written_once(self):
        rows = [_Out(a=1, b="x"), _Out(a=2, b="y")]
        raw = await _collect(DownloadableRepository._serialize_csv(_aiter(rows), None))
        # Header appears exactly once even across multiple rows.
        assert raw.decode().count("a,b") == 1

    async def test_columns_default_to_first_row_keys_when_no_fields(self):
        rows = [_Out(a=1, b="x")]
        raw = await _collect(DownloadableRepository._serialize_csv(_aiter(rows), None))
        reader = csv.reader(io.StringIO(raw.decode()))
        assert next(reader) == ["a", "b"]

    async def test_columns_follow_sorted_fields_when_given(self):
        rows = [_Out(a=1, b="x")]
        raw = await _collect(DownloadableRepository._serialize_csv(_aiter(rows), frozenset({"b", "a"})))
        reader = csv.reader(io.StringIO(raw.decode()))
        assert next(reader) == ["a", "b"]

    async def test_extra_fields_are_ignored(self):
        # 'b' is not in the requested field set -> dropped from output.
        rows = [_Out(a=1, b="x")]
        raw = await _collect(DownloadableRepository._serialize_csv(_aiter(rows), frozenset({"a"})))
        parsed = _parse_csv(raw)
        assert parsed == [{"a": "1"}]

    async def test_all_rows_emitted(self):
        rows = [_Out(a=i, b=str(i)) for i in range(5)]
        raw = await _collect(DownloadableRepository._serialize_csv(_aiter(rows), None))
        assert len(_parse_csv(raw)) == 5

    async def test_no_row_bleed_between_chunks(self):
        # Each yielded chunk after the header must contain exactly one row, proving
        # the shared StringIO buffer is truncated between iterations.
        rows = [_Out(a=1, b="x"), _Out(a=2, b="y")]
        chunks = [c async for c in DownloadableRepository._serialize_csv(_aiter(rows), None)]
        # First chunk: header + row 1; subsequent chunks: one row each.
        assert b"2,y" not in chunks[0]

    async def test_empty_input_yields_no_bytes(self):
        raw = await _collect(DownloadableRepository._serialize_csv(_aiter([]), None))
        assert raw == b""

    async def test_nested_dict_column_flattens_to_dotted_columns(self):
        """A dict-valued column is flattened into dotted-path columns, not one JSON cell.

        ``{"data": {"k": "v", "n": 1}}`` becomes the columns ``data.k`` and ``data.n`` so a
        consumer reads each leaf as its own cell rather than parsing an embedded JSON blob.
        """
        rows = [_OutWithData(name="r1", data={"k": "v", "n": 1})]
        raw = await _collect(DownloadableRepository._serialize_csv(_aiter(rows), None))
        parsed = _parse_csv(raw)[0]
        # DictReader returns every cell as a string.
        assert parsed == {"name": "r1", "data.k": "v", "data.n": "1"}


# ===========================================================================
# _csv_cell
# ===========================================================================


class TestCsvCell:
    @pytest.mark.parametrize("value", [None, "s", 1, 1.5, True])
    def test_scalar_terminates_as_a_single_cell_under_its_path(self, value: Any):
        # A scalar (or None) yields exactly one cell keyed by the column path, value verbatim.
        assert DownloadableRepository._csv_cell("col", value) == {"col": value}

    def test_nested_dict_flattens_to_dotted_paths(self):
        # {v1: {v2: {v3: 1}}} at path "v1" -> {"v1.v2.v3": 1}
        assert DownloadableRepository._csv_cell("v1", {"v2": {"v3": 1}}) == {"v1.v2.v3": 1}

    def test_each_leaf_gets_its_own_dotted_column(self):
        flat = DownloadableRepository._csv_cell("data", {"a": 1, "b": {"c": 2}})
        assert flat == {"data.a": 1, "data.b.c": 2}

    def test_list_leaf_is_json_encoded_not_exploded(self):
        assert DownloadableRepository._csv_cell("tags", [1, "x"]) == {"tags": '[1,"x"]'}

    def test_empty_dict_stays_a_single_json_cell(self):
        # No leaves to flatten, so it stays one JSON cell under its own path.
        assert DownloadableRepository._csv_cell("data", {}) == {"data": "{}"}

    def test_string_leaf_is_verbatim_not_json_escaped(self):
        # A nested string leaf is written as-is (not quoted/JSON-encoded).
        assert DownloadableRepository._csv_cell("data", {"b": "café"}) == {"data.b": "café"}

    def test_json_encoded_list_leaf_preserves_unicode(self):
        # ensure_ascii=False keeps human-readable unicode in a JSON-encoded leaf.
        assert DownloadableRepository._csv_cell("t", ["café"]) == {"t": '["café"]'}


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

    async def test_unhandled_format_raises_download_error(self):
        """An unknown format hits the ``case _`` guard and raises rather than returning None.

        The router coerces the path param to a ``DownloadFormat``, so this is defence in depth: a
        member added to the enum without a serializer case fails loudly here instead of dispatching
        to ``None`` and blowing up mid-stream.
        """
        repo = _repo()
        with pytest.raises(DownloadError):
            repo._get_serializer(cast(DownloadFormat, "xml"), None)


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
        payload = {"filter": {"created__gte": datetime(2024, 1, 1, tzinfo=UTC)}}
        digest = repo._hash_payload(payload)
        assert len(digest) == 64


# ===========================================================================
# _s3_object_exists
# ===========================================================================


def _s3_ctx(head_object: Any) -> Any:
    """An async-context-manager S3 client stand-in whose ``head_object`` is ``head_object``."""
    client = MagicMock()
    client.head_object = head_object
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


class TestS3ObjectExists:
    async def test_true_when_head_object_succeeds(self):
        repo = _repo()
        s3 = _s3_ctx(AsyncMock(return_value={"ContentLength": 10}))
        assert await repo._s3_object_exists("bucket", "key", s3) is True

    async def test_false_when_head_object_raises(self):
        # A missing object makes head_object raise (404/NoSuchKey); that is a cache miss, not an error.
        repo = _repo()
        s3 = _s3_ctx(AsyncMock(side_effect=Exception("404")))
        assert await repo._s3_object_exists("bucket", "key", s3) is False
