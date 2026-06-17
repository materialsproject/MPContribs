from unittest.mock import AsyncMock, MagicMock

import pytest
from beanie import PydanticObjectId

from mpcontribs_api.domains._shared.models import ComponentDeleteResponse, DeleteResponse
from mpcontribs_api.domains.attachments.models import AttachmentFilter
from mpcontribs_api.domains.attachments.service import AttachmentService
from mpcontribs_api.exceptions import NotFoundError

pytestmark = pytest.mark.asyncio


def _oid() -> PydanticObjectId:
    return PydanticObjectId()


def _make_service(
    *,
    candidate_ids: list[PydanticObjectId],
    reachable: set[PydanticObjectId],
    referenced: set[PydanticObjectId],
) -> tuple[AttachmentService, AsyncMock, AsyncMock]:
    """Build an AttachmentService over mocked component + contribution repos.

    ``referenced_component_ids`` returns ``reachable`` for scoped checks (access gate) and
    ``referenced`` for unscoped checks (global integrity), keyed off the ``scoped`` kwarg.
    """
    components = AsyncMock(name="components")
    components.list_ids = AsyncMock(return_value=candidate_ids)
    components.delete_by_ids = AsyncMock(side_effect=lambda ids: DeleteResponse(num_deleted=len(ids)))
    components.delete_by_id = AsyncMock(return_value=DeleteResponse(num_deleted=1))
    components._convert_object_id = MagicMock(side_effect=lambda s: PydanticObjectId(s))
    components._not_found = MagicMock(return_value="not found")

    contributions = AsyncMock(name="contributions")

    async def _referenced(ref_field, ids, *, scoped):
        pool = reachable if scoped else referenced
        return {i for i in ids if i in pool}

    contributions.referenced_component_ids = AsyncMock(side_effect=_referenced)

    return AttachmentService(components, contributions), components, contributions


# ---------------------------------------------------------------------------
# delete(filter)
# ---------------------------------------------------------------------------


async def test_delete_reachable_and_unreferenced_deletes_all():
    a, b = _oid(), _oid()
    svc, components, contributions = _make_service(
        candidate_ids=[a, b], reachable={a, b}, referenced=set()
    )

    result = await svc.delete(AttachmentFilter())

    assert isinstance(result, ComponentDeleteResponse)
    assert result.num_deleted == 2
    assert result.num_skipped == 0
    assert result.referenced_ids == []
    components.delete_by_ids.assert_awaited_once()
    assert set(components.delete_by_ids.await_args.args[0]) == {a, b}


async def test_delete_skips_globally_referenced():
    a, b = _oid(), _oid()
    svc, components, _ = _make_service(candidate_ids=[a, b], reachable={a, b}, referenced={b})

    result = await svc.delete(AttachmentFilter())

    assert result.num_deleted == 1
    assert result.num_skipped == 1
    assert result.referenced_ids == [b]
    assert components.delete_by_ids.await_args.args[0] == [a]


async def test_delete_not_reachable_deletes_nothing():
    a = _oid()
    svc, components, contributions = _make_service(candidate_ids=[a], reachable=set(), referenced={a})

    result = await svc.delete(AttachmentFilter())

    assert result.num_deleted == 0
    assert result.num_skipped == 0
    components.delete_by_ids.assert_not_awaited()
    # global check is skipped once the access gate yields nothing
    assert contributions.referenced_component_ids.await_count == 1
    assert contributions.referenced_component_ids.await_args.kwargs["scoped"] is True


async def test_delete_empty_candidate_set():
    svc, components, _ = _make_service(candidate_ids=[], reachable=set(), referenced=set())

    result = await svc.delete(AttachmentFilter())

    assert result.num_deleted == 0
    components.delete_by_ids.assert_not_awaited()


async def test_delete_checks_scoped_before_global():
    a = _oid()
    svc, _, contributions = _make_service(candidate_ids=[a], reachable={a}, referenced=set())

    await svc.delete(AttachmentFilter())

    scoped_flags = [c.kwargs["scoped"] for c in contributions.referenced_component_ids.await_args_list]
    assert scoped_flags == [True, False]


# ---------------------------------------------------------------------------
# delete_by_id(id)
# ---------------------------------------------------------------------------


async def test_delete_by_id_not_reachable_raises_not_found():
    oid = _oid()
    svc, _, _ = _make_service(candidate_ids=[], reachable=set(), referenced=set())

    with pytest.raises(NotFoundError):
        await svc.delete_by_id(str(oid))


async def test_delete_by_id_referenced_is_skipped():
    oid = _oid()
    svc, components, _ = _make_service(candidate_ids=[], reachable={oid}, referenced={oid})

    result = await svc.delete_by_id(str(oid))

    assert result.num_deleted == 0
    assert result.num_skipped == 1
    assert result.referenced_ids == [oid]
    components.delete_by_id.assert_not_awaited()


async def test_delete_by_id_reachable_and_unreferenced_deletes():
    oid = _oid()
    svc, components, _ = _make_service(candidate_ids=[], reachable={oid}, referenced=set())

    result = await svc.delete_by_id(str(oid))

    assert result.num_deleted == 1
    assert result.num_skipped == 0
    components.delete_by_id.assert_awaited_once_with(oid)
