"""Unit tests for ``ComponentService.read_content`` (the single read-only component service).

The service no longer proxies object bytes: after a reachability access check it mints a short-lived
presigned S3 GET URL, and the route 307-redirects to it. Components are immutable and content-addressed,
so the key is built straight from the record's own ``(project, hash, ext)`` —
``mpcontribs/{project}/components/{subtype}/{hash}.{ext}`` — with no owner path and no version pinning.

Components are owned by contributions (never projects), so reachability is a single contribution-reference
check. These tests pin that the access gate runs *before* any URL is minted and that the presigned request
addresses the content-addressed object.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from beanie import PydanticObjectId

from mpcontribs_api.config import get_settings
from mpcontribs_api.domains.components.service import ComponentService
from mpcontribs_api.exceptions import NotFoundError

pytestmark = pytest.mark.asyncio

PRESIGNED = "https://s3.example/presigned-get"
HASH = "a" * 64


def _make_service(
    *,
    structure: SimpleNamespace | None,
    reachable: bool = False,
) -> tuple[ComponentService, AsyncMock, AsyncMock, AsyncMock]:
    """Build a structure-configured ComponentService over mocked repos and an S3 client.

    ``structure`` is what the component repo's ``read_one`` returns (the index record, or None).
    ``reachable`` controls whether an in-scope contribution references it. The S3 client's
    ``generate_presigned_url`` returns a fixed URL so callers can assert the request parameters.
    """
    sid = {structure.id} if structure is not None else set()

    structures = AsyncMock(name="structures")
    structures.read_one = AsyncMock(return_value=structure)

    contributions = AsyncMock(name="contributions")
    contributions.referenced_component_ids = AsyncMock(return_value=sid if reachable else set())

    s3 = AsyncMock(name="s3")
    s3.generate_presigned_url = AsyncMock(return_value=PRESIGNED)

    service = ComponentService(structures, contributions, subtype="structure", ref_field="structures")
    return service, structures, contributions, s3


async def test_read_content_reachable_mints_content_addressed_get():
    oid = PydanticObjectId()
    record = SimpleNamespace(id=oid, project="my_project", hash=HASH, ext="cif")
    svc, _, contributions, s3 = _make_service(structure=record, reachable=True)

    url = await svc.read_content({"id": str(oid)}, s3=s3)

    assert url == PRESIGNED
    # Reachability is a single contribution-reference check, keyed off the resolved record id.
    contributions.referenced_component_ids.assert_awaited_once_with("structures", [oid], scoped=True)
    kwargs = s3.generate_presigned_url.await_args.kwargs
    assert kwargs["ClientMethod"] == "get_object"
    assert kwargs["ExpiresIn"] == get_settings().aws.s3.expires_in
    # Content-addressed key; no VersionId (resolves to the immutable object).
    assert kwargs["Params"] == {
        "Bucket": get_settings().aws.s3.bronze_bucket,
        "Key": f"mpcontribs/my_project/components/structures/{HASH}.cif",
    }


async def test_read_content_missing_structure_raises_before_presign():
    svc, _, contributions, s3 = _make_service(structure=None, reachable=True)

    with pytest.raises(NotFoundError):
        await svc.read_content({"id": str(PydanticObjectId())}, s3=s3)

    # No reachability lookup and no URL minted once the record is absent.
    contributions.referenced_component_ids.assert_not_awaited()
    s3.generate_presigned_url.assert_not_awaited()


async def test_read_content_unreachable_structure_raises_before_presign():
    oid = PydanticObjectId()
    record = SimpleNamespace(id=oid, project="my_project", hash=HASH, ext="cif")
    # Record exists but no in-scope contribution references it.
    svc, _, _, s3 = _make_service(structure=record, reachable=False)

    with pytest.raises(NotFoundError):
        await svc.read_content({"id": str(oid)}, s3=s3)

    s3.generate_presigned_url.assert_not_awaited()
