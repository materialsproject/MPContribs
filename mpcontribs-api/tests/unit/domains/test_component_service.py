from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from beanie import PydanticObjectId

from mpcontribs_api.domains._shared.bulk import BulkFailure
from mpcontribs_api.domains._shared.models import ComponentDeleteResponse, DeleteResponse
from mpcontribs_api.domains._shared.service import ComponentService
from mpcontribs_api.domains.attachments.models import Attachment, AttachmentFilter
from mpcontribs_api.exceptions import NotFoundError

pytestmark = pytest.mark.asyncio


def _oid() -> PydanticObjectId:
    return PydanticObjectId()


def _id_resolving_get_one() -> AsyncMock:
    """A stand-in for the component repo's ``read_one``.

    The service resolves a component's ``_id`` by asking the repo (which coerces a string ``id`` to
    ``ObjectId`` internally), so the mock echoes a document whose ``id`` is the coerced identifier —
    letting the reachability check key off the real ``ObjectId``.
    """

    async def _get_one(identifiers, fields=None, **kwargs):
        if "id" in identifiers:
            raw = identifiers["id"]
            return SimpleNamespace(id=PydanticObjectId(raw) if isinstance(raw, str) else raw)
        return None

    return AsyncMock(side_effect=_get_one)


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
    components.delete_many = AsyncMock(side_effect=lambda filter: DeleteResponse(num_deleted=len(filter.id__in)))
    components.delete_one = AsyncMock(return_value=DeleteResponse(num_deleted=1))
    components.read_one = _id_resolving_get_one()

    contributions = AsyncMock(name="contributions")

    async def _referenced(ref_field, ids=None, *, scoped):
        pool = reachable if scoped else referenced
        return set(pool) if ids is None else {i for i in ids if i in pool}

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

    result = await svc.delete_many(AttachmentFilter())

    assert isinstance(result, ComponentDeleteResponse)
    assert result.num_deleted == 2
    assert result.num_skipped == 0
    assert result.referenced_ids == []
    components.delete_many.assert_awaited_once()
    assert set(components.delete_many.await_args.args[0].id__in) == {a, b}


async def test_delete_skips_globally_referenced():
    a, b = _oid(), _oid()
    svc, components, _ = _make_service(candidate_ids=[a, b], reachable={a, b}, referenced={b})

    result = await svc.delete_many(AttachmentFilter())

    assert result.num_deleted == 1
    assert result.num_skipped == 1
    assert result.referenced_ids == [b]
    assert components.delete_many.await_args.args[0].id__in == [a]


async def test_delete_not_reachable_deletes_nothing():
    a = _oid()
    svc, components, contributions = _make_service(candidate_ids=[a], reachable=set(), referenced={a})

    result = await svc.delete_many(AttachmentFilter())

    assert result.num_deleted == 0
    assert result.num_skipped == 0
    components.delete_by_ids.assert_not_awaited()
    # global check is skipped once the access gate yields nothing
    assert contributions.referenced_component_ids.await_count == 1
    assert contributions.referenced_component_ids.await_args.kwargs["scoped"] is True


async def test_delete_empty_candidate_set():
    svc, components, _ = _make_service(candidate_ids=[], reachable=set(), referenced=set())

    result = await svc.delete_many(AttachmentFilter())

    assert result.num_deleted == 0
    components.delete_by_ids.assert_not_awaited()


async def test_delete_checks_scoped_before_global():
    a = _oid()
    svc, _, contributions = _make_service(candidate_ids=[a], reachable={a}, referenced=set())

    await svc.delete_many(AttachmentFilter())

    scoped_flags = [c.kwargs["scoped"] for c in contributions.referenced_component_ids.await_args_list]
    assert scoped_flags == [True, False]


# ---------------------------------------------------------------------------
# delete_by_id(id)
# ---------------------------------------------------------------------------


async def test_delete_by_id_not_reachable_raises_not_found():
    oid = _oid()
    svc, _, _ = _make_service(candidate_ids=[], reachable=set(), referenced=set())

    with pytest.raises(NotFoundError):
        await svc.delete_one({"id": str(oid)})


async def test_delete_by_id_referenced_is_skipped():
    oid = _oid()
    svc, components, _ = _make_service(candidate_ids=[], reachable={oid}, referenced={oid})

    result = await svc.delete_one({"id": str(oid)})

    assert result.num_deleted == 0
    assert result.num_skipped == 1
    assert result.referenced_ids == [oid]
    components.delete_one.assert_not_awaited()


async def test_delete_by_id_reachable_and_unreferenced_deletes():
    oid = _oid()
    svc, components, _ = _make_service(candidate_ids=[], reachable={oid}, referenced=set())

    result = await svc.delete_one({"id": str(oid)})

    assert result.num_deleted == 1
    assert result.num_skipped == 0
    components.delete_one.assert_awaited_once_with({"id": oid})


# ---------------------------------------------------------------------------
# Read gating: get_by_id / read_many / patch_by_id are reachability-scoped
# ---------------------------------------------------------------------------


def _make_read_service(*, reachable: set[PydanticObjectId]) -> tuple[ComponentService, AsyncMock, AsyncMock]:
    """ComponentService whose contribution repo reports `reachable` ids as in-scope."""
    components = AsyncMock(name="components")
    components.read_one = _id_resolving_get_one()

    contributions = AsyncMock(name="contributions")

    async def _referenced(ref_field, ids=None, *, scoped):
        if ids is None:
            return set(reachable) if scoped else set()
        return {i for i in ids if i in reachable} if scoped else set()

    contributions.referenced_component_ids = AsyncMock(side_effect=_referenced)

    service = ComponentService(components, contributions, ref_field="attachments")
    return service, components, contributions


async def test_get_by_id_unreachable_returns_none():
    # The id is resolved through the repo, but an unreachable component still yields None (and the
    # full-fields fetch is skipped once the reachability gate fails).
    oid = _oid()
    svc, components, _ = _make_read_service(reachable=set())

    result = await svc.read_one({"id": str(oid)}, fields=None)

    assert result is None
    components.read_one.assert_awaited_once()


async def test_get_by_id_reachable_fetches_component():
    oid = _oid()
    svc, components, _ = _make_read_service(reachable={oid})

    result = await svc.read_one({"id": str(oid)}, fields=None)

    # Resolved (id lookup) then fetched (full projection): the reachable component is returned.
    assert result is not None and result.id == oid
    assert components.read_one.await_count == 2


async def test_get_many_restricts_to_reachable_ids():
    a, b = _oid(), _oid()
    svc, components, contributions = _make_read_service(reachable={a, b})
    components.read_many = AsyncMock(return_value="page")

    await svc.read_many(filter=AttachmentFilter(), pagination=None, fields=None)

    contributions.referenced_component_ids.assert_awaited_once()
    assert contributions.referenced_component_ids.await_args.kwargs["scoped"] is True
    assert contributions.referenced_component_ids.await_args.args[1:] == ()
    restrict = components.read_many.await_args.kwargs["restrict_ids"]
    assert set(restrict) == {a, b}


async def test_patch_by_id_unreachable_raises_not_found():
    oid = _oid()
    svc, components, _ = _make_read_service(reachable=set())

    with pytest.raises(NotFoundError):
        await svc.update_one({"id": str(oid)}, update=MagicMock())
    components.update_one.assert_not_awaited()


async def test_patch_by_id_reachable_patches():
    oid = _oid()
    svc, components, _ = _make_read_service(reachable={oid})
    components.update_one = AsyncMock(return_value="patched")

    result = await svc.update_one({"id": str(oid)}, update=MagicMock())

    assert result == "patched"
    components.update_one.assert_awaited_once()


# ---------------------------------------------------------------------------
# insert_many — assembles a BulkWriteSummary from the repo's (successes, failures) tuple
# ---------------------------------------------------------------------------


async def test_insert_many_assembles_summary_sorted_by_index():
    svc, components, _ = _make_service(candidate_ids=[], reachable=set(), referenced=set())
    # spec=Attachment so the docs satisfy BulkWriteSummary's Component-typed ``succeeded`` field.
    doc_a, doc_b = MagicMock(spec=Attachment), MagicMock(spec=Attachment)
    failure = BulkFailure(index=1, error_code="conflict", message="dup")
    # Repo reports successes out of order and one per-item failure; the service orders by input index.
    components.insert_many = AsyncMock(return_value=([(2, doc_b), (0, doc_a)], [failure]))

    summary = await svc.insert_many(components=["in0", "in1", "in2"])

    assert summary.total == 3
    assert summary.succeeded == [doc_a, doc_b]  # index 0 then index 2
    assert [f.index for f in summary.failed] == [1]


async def test_insert_many_all_succeed():
    svc, components, _ = _make_service(candidate_ids=[], reachable=set(), referenced=set())
    doc = MagicMock(spec=Attachment)
    components.insert_many = AsyncMock(return_value=([(0, doc)], []))

    summary = await svc.insert_many(components=["only"])

    assert summary.total == 1
    assert summary.succeeded == [doc]
    assert summary.failed == []
