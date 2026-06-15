import csv
import gzip
import io

import pytest
from beanie import PydanticObjectId

from mpcontribs_api.auth import User
from mpcontribs_api.domains.contributions.models import Contribution, ContributionFilter
from mpcontribs_api.domains.contributions.repository import MongoDbContributionRepository

pytestmark = [pytest.mark.db, pytest.mark.asyncio(loop_scope="session")]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ADMIN = User(username="google:admin@example.com", groups=frozenset({"admin"}))
ALICE = User(username="google:alice@example.com", groups=frozenset({"mp-team"}))
ANON = User()


def _repo(user: User = ADMIN) -> MongoDbContributionRepository:
    return MongoDbContributionRepository(user)


async def _insert(project: str, identifier: str, is_public: bool, **overrides) -> Contribution:
    doc = Contribution(
        _id=PydanticObjectId(),
        project=project,
        identifier=identifier,
        formula=overrides.pop("formula", "Fe2O3"),
        data=overrides.pop("data", {"band_gap": 2.1}),
        is_public=is_public,
        **overrides,
    )
    await doc.insert()
    return doc


async def _seed_scope_fixture() -> None:
    """Three contributions spanning the three scope buckets."""
    await _insert("pub-proj", "mp-public", is_public=True)
    await _insert("mp-team", "mp-group", is_public=False)
    await _insert("secret", "mp-private", is_public=False)


async def _collect(stream) -> bytes:
    chunks: list[bytes] = []
    async for chunk in stream:
        chunks.append(chunk)
    return b"".join(chunks)


async def _download_bytes(repo: MongoDbContributionRepository, *, format="jsonl", fields=None, filter=None) -> bytes:
    from mpcontribs_api.domains._shared.types import DownloadFormat, ShortMimeFormat

    stream = await repo.download_contributions(
        format=DownloadFormat(format),
        short_mime=ShortMimeFormat.GZ,
        ignore_cache=True,
        filter=filter or ContributionFilter(),
        fields=fields,
    )
    return gzip.decompress(await _collect(stream))


def _parse_jsonl(raw: bytes) -> list[dict]:
    import json

    return [json.loads(line) for line in raw.splitlines() if line]


def _parse_csv(raw: bytes) -> list[dict]:
    return list(csv.DictReader(io.StringIO(raw.decode())))


# ---------------------------------------------------------------------------
# JSONL round-trip + scope
# ---------------------------------------------------------------------------


class TestDownloadJsonl:
    async def test_admin_downloads_all_rows(self, db):
        await _seed_scope_fixture()
        rows = _parse_jsonl(await _download_bytes(_repo(ADMIN)))
        assert {r["identifier"] for r in rows} == {"mp-public", "mp-group", "mp-private"}

    async def test_anonymous_sees_only_public(self, db):
        await _seed_scope_fixture()
        rows = _parse_jsonl(await _download_bytes(_repo(ANON)))
        assert {r["identifier"] for r in rows} == {"mp-public"}

    async def test_group_member_sees_public_and_group(self, db):
        await _seed_scope_fixture()
        rows = _parse_jsonl(await _download_bytes(_repo(ALICE)))
        assert {r["identifier"] for r in rows} == {"mp-public", "mp-group"}

    async def test_rows_carry_expected_fields(self, db):
        await _insert("pub-proj", "mp-1", is_public=True, formula="Li2O")
        rows = _parse_jsonl(await _download_bytes(_repo(ADMIN)))
        assert rows[0]["formula"] == "Li2O"
        assert rows[0]["project"] == "pub-proj"


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------


class TestDownloadFiltering:
    async def test_filter_limits_returned_rows(self, db):
        await _insert("pub-proj", "keep-me", is_public=True)
        await _insert("pub-proj", "drop-me", is_public=True)
        rows = _parse_jsonl(
            await _download_bytes(_repo(ADMIN), filter=ContributionFilter(identifier="keep-me"))
        )
        assert {r["identifier"] for r in rows} == {"keep-me"}

    async def test_empty_result_is_valid_empty_gzip(self, db):
        # No documents match -> the stream is genuinely empty and decompresses to b"".
        # (This path never enters the compress loop, so the missing-flush bug doesn't bite.)
        raw = await _download_bytes(_repo(ADMIN), filter=ContributionFilter(identifier="no-such-id"))
        assert raw == b""


# ---------------------------------------------------------------------------
# CSV round-trip + field projection
# ---------------------------------------------------------------------------


class TestDownloadCsv:
    async def test_csv_has_header_and_rows(self, db):
        await _insert("pub-proj", "mp-1", is_public=True)
        await _insert("pub-proj", "mp-2", is_public=True)
        rows = _parse_csv(await _download_bytes(_repo(ADMIN), format="csv"))
        assert len(rows) == 2

    async def test_csv_projects_only_requested_fields(self, db):
        await _insert("pub-proj", "mp-1", is_public=True)
        fields = frozenset({"id", "identifier"})
        rows = _parse_csv(await _download_bytes(_repo(ADMIN), format="csv", fields=fields))
        # Only the requested columns (plus the always-present id) appear.
        assert set(rows[0].keys()) <= {"id", "identifier"}
        assert rows[0]["identifier"] == "mp-1"
