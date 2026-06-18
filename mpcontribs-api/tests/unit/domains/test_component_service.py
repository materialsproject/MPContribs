from unittest.mock import AsyncMock, MagicMock

import pytest
from beanie import PydanticObjectId

from mpcontribs_api.domains._shared.models import ComponentDeleteResponse, DeleteResponse
from mpcontribs_api.domains._shared.service import ComponentService
from mpcontribs_api.domains.attachments.models import AttachmentFilter
from mpcontribs_api.exceptions import NotFoundError

pytestmark = pytest.mark.asyncio


def _oid() -> PydanticObjectId:
    return PydanticObjectId()


def _make_service(
    *,
    candidate_ids: list[PydanticObjectId],
    reachable: set[PydanticObjectId],
    referenced: set[PydanticObjectId],
) -> tuple[ComponentService, AsyncMock, AsyncMock]:
    """Build a ComponentService over mocked component + contribution repos.

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

    service = ComponentService(components, contributions, ref_field="attachments")
    return service, components, contributions


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


# ---------------------------------------------------------------------------
# Read gating: get_by_id / get_many / patch_by_id are reachability-scoped
# ---------------------------------------------------------------------------


def _make_read_service(*, reachable: set[PydanticObjectId]) -> tuple[ComponentService, AsyncMock, AsyncMock]:
    """ComponentService whose contribution repo reports `reachable` ids as in-scope."""
    components = AsyncMock(name="components")
    components._convert_object_id = MagicMock(side_effect=lambda s: PydanticObjectId(s))
    components._not_found = MagicMock(return_value="not found")

    contributions = AsyncMock(name="contributions")

    async def _referenced(ref_field, ids, *, scoped):
        return {i for i in ids if i in reachable} if scoped else set()

    contributions.referenced_component_ids = AsyncMock(side_effect=_referenced)
    contributions.list_referenced_component_ids = AsyncMock(return_value=reachable)

    service = ComponentService(components, contributions, ref_field="attachments")
    return service, components, contributions


async def test_get_by_id_unreachable_returns_none_without_fetch():
    oid = _oid()
    svc, components, _ = _make_read_service(reachable=set())

    result = await svc.get_by_id(str(oid), fields=None)

    assert result is None
    components.get_component_by_id.assert_not_awaited()


async def test_get_by_id_reachable_fetches_component():
    oid = _oid()
    svc, components, _ = _make_read_service(reachable={oid})
    components.get_component_by_id = AsyncMock(return_value="the-component")

    result = await svc.get_by_id(str(oid), fields=None)

    assert result == "the-component"
    components.get_component_by_id.assert_awaited_once()


async def test_get_many_restricts_to_reachable_ids():
    a, b = _oid(), _oid()
    svc, components, contributions = _make_read_service(reachable={a, b})
    components.get_many = AsyncMock(return_value="page")

    await svc.get_many(filter=AttachmentFilter(), pagination=None, fields=None)

    contributions.list_referenced_component_ids.assert_awaited_once()
    assert contributions.list_referenced_component_ids.await_args.kwargs["scoped"] is True
    restrict = components.get_many.await_args.kwargs["restrict_ids"]
    assert set(restrict) == {a, b}


async def test_patch_by_id_unreachable_raises_not_found():
    oid = _oid()
    svc, components, _ = _make_read_service(reachable=set())

    with pytest.raises(NotFoundError):
        await svc.patch_by_id(str(oid), update=MagicMock())
    components.patch_component_by_id.assert_not_awaited()


async def test_patch_by_id_reachable_patches():
    oid = _oid()
    svc, components, _ = _make_read_service(reachable={oid})
    components.patch_component_by_id = AsyncMock(return_value="patched")

    result = await svc.patch_by_id(str(oid), update=MagicMock())

    assert result == "patched"
    components.patch_component_by_id.assert_awaited_once()
