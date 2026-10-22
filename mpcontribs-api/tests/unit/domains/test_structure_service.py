"""Unit tests for ``StructureService.read_content``.

The service no longer proxies object bytes: after the contribution-reachability access check it mints a
short-lived presigned S3 GET URL, and the route 307-redirects to it. These tests pin that the access
gate still runs *before* any URL is minted, and that the presigned request addresses the exact
version-pinned object (bucket / ``{project}/structures/{name}`` key / ``VersionId``). The key is built
straight from the record's own ``project``/``name`` — no contribution round trip is needed to locate it.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from beanie import PydanticObjectId

from mpcontribs_api.config import get_settings
from mpcontribs_api.domains.structures.service import StructureService
from mpcontribs_api.exceptions import NotFoundError

pytestmark = pytest.mark.asyncio

PRESIGNED = "https://s3.example/presigned-get"


def _make_service(
    *,
    structure: SimpleNamespace | None,
    reachable: bool,
) -> tuple[StructureService, AsyncMock, AsyncMock, AsyncMock]:
    """Build a StructureService over mocked structure + contribution repos and a mocked S3 client.

    ``structure`` is what the structure repo's ``read_one`` returns (the index record, or None), and
    ``reachable`` controls whether an in-scope contribution references it: the contribution repo's
    ``referenced_component_ids`` returns the record id (reachable) or an empty set (unreachable). The
    S3 client's ``generate_presigned_url`` returns a fixed URL so callers can assert both the returned
    value and the exact request parameters.
    """
    structures = AsyncMock(name="structures")
    structures.read_one = AsyncMock(return_value=structure)

    reached = {structure.id} if reachable and structure is not None else set()
    contributions = AsyncMock(name="contributions")
    contributions.referenced_component_ids = AsyncMock(return_value=reached)

    s3 = AsyncMock(name="s3")
    s3.generate_presigned_url = AsyncMock(return_value=PRESIGNED)

    return StructureService(structures, contributions), structures, contributions, s3


async def test_read_content_mints_version_pinned_presigned_get():
    oid = PydanticObjectId()
    record = SimpleNamespace(id=oid, project="my_project", name="Fe2O3.cif", s3_version_id="v-abc123")
    svc, _, contributions, s3 = _make_service(structure=record, reachable=True)

    url = await svc.read_content({"id": str(oid)}, s3=s3)

    assert url == PRESIGNED
    # Access gate keyed off the resolved record id, not the raw identifiers.
    contributions.referenced_component_ids.assert_awaited_once_with("structures", [oid], scoped=True)
    s3.generate_presigned_url.assert_awaited_once()
    kwargs = s3.generate_presigned_url.await_args.kwargs
    assert kwargs["ClientMethod"] == "get_object"
    assert kwargs["ExpiresIn"] == get_settings().aws.s3.expires_in
    assert kwargs["Params"] == {
        "Bucket": get_settings().aws.s3.processed_data_bucket,
        "Key": "my_project/structures/Fe2O3.cif",
        "VersionId": "v-abc123",
    }


@pytest.mark.parametrize("version", [None, ""])
async def test_read_content_omits_versionid_when_absent(version):
    # A record without a pinned version must not sign a literal empty ``VersionId`` (which would
    # address a non-existent version rather than the current object).
    oid = PydanticObjectId()
    record = SimpleNamespace(id=oid, project="my_project", name="Fe2O3.cif", s3_version_id=version)
    svc, _, _, s3 = _make_service(structure=record, reachable=True)

    await svc.read_content({"id": str(oid)}, s3=s3)

    assert "VersionId" not in s3.generate_presigned_url.await_args.kwargs["Params"]


async def test_read_content_missing_structure_raises_before_presign():
    svc, _, contributions, s3 = _make_service(structure=None, reachable=True)

    with pytest.raises(NotFoundError):
        await svc.read_content({"id": str(PydanticObjectId())}, s3=s3)

    # No reachability lookup and no URL minted once the record is absent.
    contributions.referenced_component_ids.assert_not_awaited()
    s3.generate_presigned_url.assert_not_awaited()


async def test_read_content_unreachable_structure_raises_before_presign():
    oid = PydanticObjectId()
    record = SimpleNamespace(id=oid, project="my_project", name="Fe2O3.cif", s3_version_id="v1")
    # Record exists but no in-scope contribution references it -> gate returns an empty set.
    svc, _, _, s3 = _make_service(structure=record, reachable=False)

    with pytest.raises(NotFoundError):
        await svc.read_content({"id": str(oid)}, s3=s3)

    s3.generate_presigned_url.assert_not_awaited()
