"""Unit tests for the read-only ``ComponentService`` reachability gating.

Components carry no access field of their own; they are owned by, and visible iff referenced by, an
in-scope contribution. The service exposes reads only — list, fetch, and a presigned GET (covered in
``test_structure_service``) — so these tests pin that ``read_many`` and ``read_one`` honor the
contribution-reference gate and never surface an unreachable component.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from beanie import PydanticObjectId

from mpcontribs_api.domains.attachments.models import AttachmentFilter, AttachmentOut
from mpcontribs_api.domains.components.service import ComponentService

pytestmark = pytest.mark.asyncio


def _oid() -> PydanticObjectId:
    return PydanticObjectId()


def _id_resolving_read_one() -> AsyncMock:
    """Stand-in for the component repo's ``read_one`` that echoes a doc whose ``id`` is the identifier.

    The service resolves a component's ``_id`` by asking the repo (which coerces a string ``id`` to
    ``ObjectId``), so the mock returns a document keyed on the coerced id for the reachability check.
    """

    async def _read_one(identifiers, fields=None, **kwargs):
        if "id" in identifiers:
            raw = identifiers["id"]
            return SimpleNamespace(id=PydanticObjectId(raw) if isinstance(raw, str) else raw)
        return None

    return AsyncMock(side_effect=_read_one)


def _make_service(*, reachable: set[PydanticObjectId] | None = None) -> tuple[ComponentService, AsyncMock, AsyncMock]:
    """Build a read-only ComponentService over mocked component/contribution repos.

    ``reachable`` is the id set the contribution repo reports as in-scope; the mock honors the
    candidate-list semantics (``ids is None`` enumerates; a list returns the reachable subset).
    """
    pool = reachable or set()

    components = AsyncMock(name="components")
    components.out_model = AttachmentOut
    components.read_one = _id_resolving_read_one()
    components.read_many = AsyncMock(return_value="page")

    async def _referenced(ref_field, ids=None, *, scoped):
        return set(pool) if ids is None else {i for i in ids if i in pool}

    contributions = AsyncMock(name="contributions")
    contributions.referenced_component_ids = AsyncMock(side_effect=_referenced)

    service = ComponentService(components, contributions, subtype="attachment", ref_field="attachments")
    return service, components, contributions


# ---------------------------------------------------------------------------
# read_one — contribution-reference gate
# ---------------------------------------------------------------------------


async def test_read_one_reachable_fetches_component():
    oid = _oid()
    svc, components, _ = _make_service(reachable={oid})

    result = await svc.read_one({"id": str(oid)}, fields=None)

    # Resolved (id lookup) then fetched (full projection): the reachable component is returned.
    assert result is not None and result.id == oid
    assert components.read_one.await_count == 2


async def test_read_one_unreachable_returns_none():
    oid = _oid()
    svc, components, _ = _make_service()  # no contribution references it

    assert await svc.read_one({"id": str(oid)}, fields=None) is None
    # Only the id-resolution read happens; the full-fields fetch is skipped once the gate fails.
    assert components.read_one.await_count == 1


async def test_read_one_missing_returns_none():
    svc, components, _ = _make_service(reachable={_oid()})
    components.read_one = AsyncMock(return_value=None)  # id resolves to no document
    assert await svc.read_one({"id": str(_oid())}, fields=None) is None


# ---------------------------------------------------------------------------
# read_many — restricts to reachable ids
# ---------------------------------------------------------------------------


async def test_read_many_restricts_to_reachable_ids():
    a, b = _oid(), _oid()
    svc, components, contributions = _make_service(reachable={a, b})

    await svc.read_many(filter=AttachmentFilter(), pagination=None, fields=None)

    contributions.referenced_component_ids.assert_awaited_once()
    assert contributions.referenced_component_ids.await_args.kwargs["scoped"] is True
    restrict = components.read_many.await_args.kwargs["restrict_ids"]
    assert set(restrict) == {a, b}


async def test_read_many_empty_when_nothing_reachable():
    svc, components, _ = _make_service()

    await svc.read_many(filter=AttachmentFilter(), pagination=None, fields=None)

    assert set(components.read_many.await_args.kwargs["restrict_ids"]) == set()
