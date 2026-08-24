import pytest

from mpcontribs_api.authz import User
from mpcontribs_api.config import get_settings
from mpcontribs_api.domains.consumers.models import (
    Consumer,
    ConsumerIn,
    ConsumerPatch,
    ConsumerSettings,
)
from mpcontribs_api.domains.consumers.repository import MongoDbConsumerRepository
from mpcontribs_api.domains.consumers.service import ConsumerService
from mpcontribs_api.exceptions import ConflictError, NotFoundError

# Same loop-scope contract as the other db suites (see test_projects_repository).
pytestmark = [pytest.mark.db, pytest.mark.asyncio(loop_scope="session")]


ADMIN = User(username="google:admin@example.com", groups=frozenset({"admin"}))


def _repo() -> MongoDbConsumerRepository:
    # Consumer management is admin-only and unscoped, so the acting user is immaterial here.
    return MongoDbConsumerRepository(ADMIN)


async def _insert(consumer: ConsumerIn) -> Consumer:
    """Persist a consumer the way the service does: build the document, then hand it to the repo.

    The repository is document-in, so the input→document conversion (``from_input_model``, which
    resolves the settings snapshot) lives here rather than in the repo.
    """
    return await _repo().insert_one(Consumer.from_input_model(consumer))


# ---------------------------------------------------------------------------
# insert_one / get_one (by consumer_id)
# ---------------------------------------------------------------------------


class TestInsertAndLookup:
    async def test_insert_then_lookup_by_consumer_id(self, db):
        await _insert(ConsumerIn(consumer_id="kong-1"))
        found = await _repo().get_one({"consumer_id": "kong-1"})
        assert found is not None
        assert found.consumer_id == "kong-1"

    async def test_duplicate_consumer_id_raises_conflict(self, db):
        await _insert(ConsumerIn(consumer_id="kong-dup"))
        with pytest.raises(ConflictError):
            await _insert(ConsumerIn(consumer_id="kong-dup"))

    async def test_lookup_missing_returns_none(self, db):
        assert await _repo().get_one({"consumer_id": "kong-absent"}) is None

    async def test_partial_override_snapshots_defaults_for_siblings(self, db):
        # Admin overrides only max_projects; the stored document must carry a fully-resolved
        # settings block, with untouched limits snapshotted from the global defaults.
        await _insert(
            ConsumerIn(consumer_id="kong-partial", settings=ConsumerSettings(max_projects=1))
        )
        stored = await _repo().get_one({"consumer_id": "kong-partial"})
        assert stored is not None
        assert stored.settings is not None
        assert stored.settings.max_projects == 1
        assert stored.settings.max_columns == get_settings().consumer.max_columns


# ---------------------------------------------------------------------------
# get_one (document id)
# ---------------------------------------------------------------------------


class TestGetByDocumentId:
    async def test_returns_out_model(self, db):
        created = await _insert(ConsumerIn(consumer_id="kong-doc"))
        result = await _repo().get_one({"id": created.id}, None)
        assert result is not None
        assert result.consumer_id == "kong-doc"

    async def test_missing_returns_none(self, db):
        from beanie import PydanticObjectId

        result = await _repo().get_one({"id": PydanticObjectId()}, None)
        assert result is None


# ---------------------------------------------------------------------------
# patch_one — partial, sibling-preserving
# ---------------------------------------------------------------------------


class TestPatchConsumer:
    async def test_patch_changes_only_named_limit(self, db):
        created = await _insert(ConsumerIn(consumer_id="kong-patch"))
        original_columns = created.settings.max_columns

        updated = await _repo().patch_one(
            {"id": created.id},
            update=ConsumerPatch(settings=ConsumerSettings(max_projects=1)),
        )
        assert updated.settings.max_projects == 1
        # Sibling limit untouched: a nested-key $set, not a whole-subdocument replace.
        assert updated.settings.max_columns == original_columns

    async def test_empty_patch_returns_existing_unchanged(self, db):
        created = await _insert(ConsumerIn(consumer_id="kong-noop"))
        result = await _repo().patch_one({"id": created.id}, update=ConsumerPatch())
        assert result.consumer_id == "kong-noop"
        assert result.settings.max_projects == created.settings.max_projects

    async def test_patch_missing_raises_not_found(self, db):
        from beanie import PydanticObjectId

        with pytest.raises(NotFoundError):
            await _repo().patch_one(
                {"id": PydanticObjectId()},
                update=ConsumerPatch(settings=ConsumerSettings(max_projects=1)),
            )


# ---------------------------------------------------------------------------
# delete_one
# ---------------------------------------------------------------------------


class TestDeleteConsumer:
    async def test_delete_removes_override(self, db):
        created = await _insert(ConsumerIn(consumer_id="kong-del"))
        await _repo().delete_one({"id": created.id})
        assert await _repo().get_one({"consumer_id": "kong-del"}) is None

    async def test_delete_missing_raises_not_found(self, db):
        from beanie import PydanticObjectId

        with pytest.raises(NotFoundError):
            await _repo().delete_one({"id": PydanticObjectId()})


# ---------------------------------------------------------------------------
# upsert_many — the base repository's concurrent, per-item-reporting bulk upsert
# ---------------------------------------------------------------------------


class TestUpsertMany:
    """The inherited ``MongoDbRepository.upsert_many`` upserts concurrently and reports per item.

    Consumers exercise the base default directly: they use the base repository and carry a unique
    index (``consumer_id``) so a colliding item produces a real per-item conflict.
    """

    async def test_all_succeed(self, db):
        docs = [Consumer.from_input_model(ConsumerIn(consumer_id=f"kong-up-{i}")) for i in range(3)]
        summary = await _repo().upsert_many(docs)
        assert summary.total == 3
        assert summary.failed == []
        assert {c.consumer_id for c in summary.succeeded} == {"kong-up-0", "kong-up-1", "kong-up-2"}
        # All three are actually persisted.
        for i in range(3):
            assert await _repo().get_one({"consumer_id": f"kong-up-{i}"}) is not None

    async def test_one_conflict_does_not_abort_the_batch(self, db):
        # Pre-existing consumer occupies the unique consumer_id the middle item will collide with.
        await _insert(ConsumerIn(consumer_id="kong-taken"))
        docs = [
            Consumer.from_input_model(ConsumerIn(consumer_id="kong-fresh-a")),
            Consumer.from_input_model(ConsumerIn(consumer_id="kong-taken")),  # unique-index conflict
            Consumer.from_input_model(ConsumerIn(consumer_id="kong-fresh-b")),
        ]
        summary = await _repo().upsert_many(docs)

        assert summary.total == 3
        # The conflict is reported at its input index, not raised; the siblings still commit.
        assert [f.index for f in summary.failed] == [1]
        assert summary.failed[0].error_code == "conflict"
        assert {c.consumer_id for c in summary.succeeded} == {"kong-fresh-a", "kong-fresh-b"}
        assert await _repo().get_one({"consumer_id": "kong-fresh-a"}) is not None
        assert await _repo().get_one({"consumer_id": "kong-fresh-b"}) is not None

    async def test_empty_batch_is_a_noop_summary(self, db):
        summary = await _repo().upsert_many([])
        assert summary.total == 0
        assert summary.succeeded == []
        assert summary.failed == []


# ---------------------------------------------------------------------------
# ConsumerService.effective_limits — the resolution actually consumed by the write paths
# ---------------------------------------------------------------------------


def _service(user: User) -> ConsumerService:
    """A ConsumerService wired like the FastAPI factory, for ``user``."""
    return ConsumerService(consumer=MongoDbConsumerRepository(user))


class TestEffectiveLimits:
    async def test_no_consumer_id_returns_defaults_without_lookup(self, db):
        # A caller with no Kong consumer_id (anonymous/dev) never touches the override collection.
        user = User(username="google:alice@example.com", groups=frozenset())
        limits = await _service(user).effective_limits(user.consumer_id)
        assert limits.max_projects == get_settings().consumer.max_projects

    async def test_stored_override_is_returned(self, db):
        await _insert(
            ConsumerIn(consumer_id="kong-eff", settings=ConsumerSettings(max_projects=42))
        )
        user = User(consumer_id="kong-eff", username="google:alice@example.com", groups=frozenset())
        limits = await _service(user).effective_limits(user.consumer_id)
        assert limits.max_projects == 42

    async def test_consumer_id_without_override_falls_back_to_defaults(self, db):
        user = User(consumer_id="kong-unknown", username="google:alice@example.com", groups=frozenset())
        limits = await _service(user).effective_limits(user.consumer_id)
        assert limits.max_projects == get_settings().consumer.max_projects
