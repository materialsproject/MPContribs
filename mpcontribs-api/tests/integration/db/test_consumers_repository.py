import pytest

from mpcontribs_api.authz import User
from mpcontribs_api.config import get_settings
from mpcontribs_api.domains.consumers.models import (
    Consumer,
    ConsumerIn,
    ConsumerPatch,
    ConsumerProjectSettings,
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
# insert_one / read_one (by consumer_id)
# ---------------------------------------------------------------------------


class TestInsertAndLookup:
    async def test_insert_then_lookup_by_consumer_id(self, db):
        await _insert(ConsumerIn(consumer_id="kong-1"))
        found = await _repo().read_one({"consumer_id": "kong-1"})
        assert found is not None
        assert found.consumer_id == "kong-1"

    async def test_duplicate_consumer_id_raises_conflict(self, db):
        await _insert(ConsumerIn(consumer_id="kong-dup"))
        with pytest.raises(ConflictError):
            await _insert(ConsumerIn(consumer_id="kong-dup"))

    async def test_lookup_missing_returns_none(self, db):
        assert await _repo().read_one({"consumer_id": "kong-absent"}) is None

    async def test_partial_override_stores_only_set_leaves(self, db):
        # Admin overrides only max_projects; the stored override is sparse — untouched limits are NOT
        # snapshotted, they stay unset and inherit the global at resolve time.
        await _insert(
            ConsumerIn(
                consumer_id="kong-partial", settings=ConsumerSettings(project=ConsumerProjectSettings(max_projects=1))
            )
        )
        stored = await _repo().read_one({"consumer_id": "kong-partial"})
        assert stored is not None
        assert stored.settings is not None
        assert stored.settings.project is not None
        assert stored.settings.project.max_projects == 1
        assert stored.settings.project.max_columns is None  # sibling leaf not snapshotted


# ---------------------------------------------------------------------------
# read_one (document id)
# ---------------------------------------------------------------------------


class TestGetByDocumentId:
    async def test_returns_out_model(self, db):
        created = await _insert(ConsumerIn(consumer_id="kong-doc"))
        result = await _repo().read_one({"id": created.id}, None)
        assert result is not None
        assert result.consumer_id == "kong-doc"

    async def test_missing_returns_none(self, db):
        from beanie import PydanticObjectId

        result = await _repo().read_one({"id": PydanticObjectId()}, None)
        assert result is None


# ---------------------------------------------------------------------------
# update_one — partial, sibling-preserving
# ---------------------------------------------------------------------------


class TestPatchConsumer:
    async def test_patch_changes_only_named_leaf(self, db):
        # Seed two project leaves, patch one, and confirm the other survives: the repo dots the update
        # to settings.<domain>.<leaf>, not a whole-subdocument replace.
        created = await _insert(
            ConsumerIn(
                consumer_id="kong-patch",
                settings=ConsumerSettings(project=ConsumerProjectSettings(max_projects=3, max_columns=20)),
            )
        )
        updated = await _repo().update_one(
            {"id": created.id},
            update=ConsumerPatch(settings=ConsumerSettings(project=ConsumerProjectSettings(max_projects=1))),
        )
        assert updated.settings.project.max_projects == 1
        assert updated.settings.project.max_columns == 20  # sibling leaf untouched

    async def test_empty_patch_returns_existing_unchanged(self, db):
        created = await _insert(
            ConsumerIn(consumer_id="kong-noop", settings=ConsumerSettings(project=ConsumerProjectSettings(max_projects=4)))
        )
        result = await _repo().update_one({"id": created.id}, update=ConsumerPatch())
        assert result.consumer_id == "kong-noop"
        assert result.settings.project.max_projects == 4

    async def test_patch_missing_raises_not_found(self, db):
        from beanie import PydanticObjectId

        with pytest.raises(NotFoundError):
            await _repo().update_one(
                {"id": PydanticObjectId()},
                update=ConsumerPatch(settings=ConsumerSettings(project=ConsumerProjectSettings(max_projects=1))),
            )


# ---------------------------------------------------------------------------
# delete_one
# ---------------------------------------------------------------------------


class TestDeleteConsumer:
    async def test_delete_removes_override(self, db):
        created = await _insert(ConsumerIn(consumer_id="kong-del"))
        await _repo().delete_one({"id": created.id})
        assert await _repo().read_one({"consumer_id": "kong-del"}) is None

    async def test_delete_missing_raises_not_found(self, db):
        from beanie import PydanticObjectId

        with pytest.raises(NotFoundError):
            await _repo().delete_one({"id": PydanticObjectId()})


# ---------------------------------------------------------------------------
# upsert_many — the base repository's concurrent, per-item-reporting bulk upsert
# ---------------------------------------------------------------------------


class TestUpsertMany:
    """The inherited ``MongoDbRepository.upsert_many`` upserts concurrently and reports per item.

    Consumers exercise the base default directly. Their identity (``consumer_id``) *is* the only
    unique key, so upsert-by-natural-key is idempotent here: a re-submitted ``consumer_id`` merges
    into the existing override rather than conflicting. (A genuine per-item conflict — a new identity
    colliding with a *separate* unique value — is exercised in the contributions suite instead.)
    """

    async def test_all_succeed(self, db):
        docs = [Consumer.from_input_model(ConsumerIn(consumer_id=f"kong-up-{i}")) for i in range(3)]
        summary = await _repo().upsert_many(docs)
        assert summary.total == 3
        assert summary.failed == []
        assert {c.consumer_id for c in summary.succeeded} == {"kong-up-0", "kong-up-1", "kong-up-2"}
        # All three are actually persisted.
        for i in range(3):
            assert await _repo().read_one({"consumer_id": f"kong-up-{i}"}) is not None

    async def test_reupserting_an_existing_id_merges_without_aborting_the_batch(self, db):
        # Pre-existing override the middle item re-submits under the same consumer_id.
        await _insert(
            ConsumerIn(
                consumer_id="kong-taken",
                settings=ConsumerSettings(project=ConsumerProjectSettings(max_projects=1)),
            )
        )
        docs = [
            Consumer.from_input_model(ConsumerIn(consumer_id="kong-fresh-a")),
            Consumer.from_input_model(  # same identity → merges into the existing override, no conflict
                ConsumerIn(
                    consumer_id="kong-taken",
                    settings=ConsumerSettings(project=ConsumerProjectSettings(max_projects=99)),
                )
            ),
            Consumer.from_input_model(ConsumerIn(consumer_id="kong-fresh-b")),
        ]
        summary = await _repo().upsert_many(docs)

        assert summary.total == 3
        # Natural-key upsert is idempotent: the duplicate identity updates in place rather than failing.
        assert summary.failed == []
        assert {c.consumer_id for c in summary.succeeded} == {"kong-fresh-a", "kong-taken", "kong-fresh-b"}
        # The re-submitted override updated the existing document rather than inserting a second one.
        merged = await _repo().read_one({"consumer_id": "kong-taken"})
        assert merged is not None
        assert merged.settings.project is not None
        assert merged.settings.project.max_projects == 99
        assert await _repo().read_one({"consumer_id": "kong-fresh-a"}) is not None
        assert await _repo().read_one({"consumer_id": "kong-fresh-b"}) is not None

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
        assert limits.project.max_projects == get_settings().consumer.project.max_projects

    async def test_stored_override_is_returned(self, db):
        await _insert(
            ConsumerIn(consumer_id="kong-eff", settings=ConsumerSettings(project=ConsumerProjectSettings(max_projects=42)))
        )
        user = User(consumer_id="kong-eff", username="google:alice@example.com", groups=frozenset())
        limits = await _service(user).effective_limits(user.consumer_id)
        assert limits.project.max_projects == 42

    async def test_consumer_id_without_override_falls_back_to_defaults(self, db):
        user = User(consumer_id="kong-unknown", username="google:alice@example.com", groups=frozenset())
        limits = await _service(user).effective_limits(user.consumer_id)
        assert limits.project.max_projects == get_settings().consumer.project.max_projects
