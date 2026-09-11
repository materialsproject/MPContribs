"""Unit tests for the shared Atlas Search abstraction (`domains/_shared/search_index.py`).

Covers the three seams the abstraction now owns so repositories never touch raw Mongo:

* ``SearchQuery`` pipeline construction — the ``$search`` stage and the fluent post-stages in order.
  The builder is scope-agnostic (it may one day merge into Beanie); scope is not its concern.
* Index management — ``sync_search_indexes`` create/update/skip idempotency and the non-fatal
  ``sync_all_search_indexes`` orchestrator, driven against a mocked collection.
* The two repositories' ``search`` methods end to end (builder + scope injection + mapping) against a
  mocked pymongo collection, locking the exact pipeline each produces — including where the read
  scope ``$match`` lands (right after ``$search``) and the contributions ``$sort``-before-``$limit``
  fix.
"""

from typing import Any, ClassVar
from unittest.mock import AsyncMock, MagicMock

import pytest
from pymongo.errors import OperationFailure
from pymongo.operations import SearchIndexModel

from mpcontribs_api.authz import User
from mpcontribs_api.domains._shared.search_index import (
    WILDCARD_PATH,
    SearchIndex,
    SearchIndexed,
    SearchIndexSyncStatus,
    SearchQuery,
    _is_subset,
    sync_all_search_indexes,
)
from mpcontribs_api.domains.contributions.models import Contribution, ContributionSearchIndex
from mpcontribs_api.domains.contributions.repository import MongoDbContributionRepository
from mpcontribs_api.domains.projects.models import Project, ProjectSearchIndex
from mpcontribs_api.domains.projects.repository import MongoDbProjectRepository

pytestmark = pytest.mark.base

INDEX = SearchIndex(name="formula_autocomplete", type="search", definition={"mappings": {"dynamic": False}})


async def _aiter(items: list[dict[str, Any]]):
    for item in items:
        yield item


def _collection(existing: list[dict[str, Any]] | None = None) -> MagicMock:
    """A fake async pymongo collection exposing the search-index + aggregate coroutines we call."""
    collection = MagicMock()
    collection.list_search_indexes = AsyncMock(return_value=_aiter(existing or []))
    collection.create_search_index = AsyncMock()
    collection.update_search_index = AsyncMock()
    return collection


def _aggregating_collection(rows: list[dict[str, Any]]) -> MagicMock:
    collection = MagicMock()
    collection.aggregate = AsyncMock(return_value=_aiter(rows))
    return collection


# ---------------------------------------------------------------------------
# SearchQuery — pipeline construction
# ---------------------------------------------------------------------------


class TestSearchQueryToPipeline:
    def test_search_is_always_first_stage(self):
        pipeline = SearchQuery(index_name="idx", operator={"text": {"query": "x", "path": "f"}}).to_pipeline()
        assert pipeline == [{"$search": {"index": "idx", "text": {"query": "x", "path": "f"}}}]

    def test_builder_carries_no_scope(self):
        # SearchQuery is scope-agnostic: rendering it never injects a $match. Scope is the caller's
        # job (see MongoDbRepository._run_search and the repository tests below).
        query = SearchQuery(index_name="idx", operator={"text": {"query": "x", "path": "f"}}).project({"_id": 1})
        assert query.to_pipeline() == [
            {"$search": {"index": "idx", "text": {"query": "x", "path": "f"}}},
            {"$project": {"_id": 1}},
        ]

    def test_stages_appended_in_call_order(self):
        query = (
            SearchQuery(index_name="idx", operator={"text": {"query": ["a"], "path": "f"}})
            .project({"f": 1})
            .match({"len": {"$gte": 1}})
            .sort({"len": 1})
            .limit(5)
        )
        assert query.to_pipeline() == [
            {"$search": {"index": "idx", "text": {"query": ["a"], "path": "f"}}},
            {"$project": {"f": 1}},
            {"$match": {"len": {"$gte": 1}}},
            {"$sort": {"len": 1}},
            {"$limit": 5},
        ]

    def test_builder_is_immutable(self):
        base = SearchQuery(index_name="idx", operator={"text": {"query": "x", "path": "f"}})
        base.limit(3)  # returns a new query; must not mutate base
        assert base.stages == ()


class TestSearchIndexText:
    def test_text_seeds_operator_with_index_name(self):
        query = INDEX.text(query=["Fe2O3"], path="formula")
        assert query.index_name == "formula_autocomplete"
        assert query.operator == {"text": {"query": ["Fe2O3"], "path": "formula"}}

    def test_wildcard_path(self):
        query = INDEX.text(query="solar", path=WILDCARD_PATH)
        assert query.operator == {"text": {"query": "solar", "path": {"wildcard": "*"}}}


# ---------------------------------------------------------------------------
# Definition diffing
# ---------------------------------------------------------------------------


class TestIsSubset:
    def test_extra_keys_in_actual_are_ignored(self):
        # Atlas echoes definitions back with server-injected defaults; those must not read as drift.
        assert _is_subset({"mappings": {"dynamic": True}}, {"mappings": {"dynamic": True}, "analyzer": "lucene"})

    def test_changed_value_is_drift(self):
        assert not _is_subset({"mappings": {"dynamic": True}}, {"mappings": {"dynamic": False}})

    def test_missing_key_is_drift(self):
        assert not _is_subset({"mappings": {"dynamic": True}}, {"other": 1})

    def test_lists_compared_by_position_and_length(self):
        assert _is_subset([{"type": "string"}], [{"type": "string"}])
        assert not _is_subset([{"type": "string"}], [{"type": "string"}, {"type": "stringFacet"}])

    def test_is_current_reads_latest_definition(self):
        index = SearchIndex(name="i", type="search", definition={"mappings": {"dynamic": True}})
        assert index.is_current({"latestDefinition": {"mappings": {"dynamic": True}, "storedSource": True}})
        assert not index.is_current({"latestDefinition": {"mappings": {"dynamic": False}}})


# ---------------------------------------------------------------------------
# Model declarations
# ---------------------------------------------------------------------------


class TestModelDeclarations:
    def test_get_search_index_returns_declared_index(self):
        index = Contribution.get_search_index(ContributionSearchIndex.FORMULA_AUTOCOMPLETE)
        assert index.name == "formula_autocomplete"
        assert index.type == "search"

    def test_get_search_index_unknown_name_raises(self):
        with pytest.raises(KeyError):
            Project.get_search_index("does-not-exist")

    def test_project_index_name_is_env_neutral(self):
        # The legacy name carried a hardcoded `-dev-`; now that the app creates the index it is neutral.
        assert ProjectSearchIndex.SEARCH == "project-search"
        assert Project.get_search_index(ProjectSearchIndex.SEARCH).name == "project-search"

    def test_contribution_definition_paths_exist_on_model(self):
        # `_path` fails loudly on drift, so a successful declaration proves the indexed fields exist.
        (index,) = Contribution.search_indexes()
        fields = index.definition["mappings"]["fields"]
        assert {"formula", "material_id", "project"} <= set(fields)


# ---------------------------------------------------------------------------
# Index management — sync_search_indexes
# ---------------------------------------------------------------------------


def _indexed(indexes: tuple[SearchIndex, ...], collection: MagicMock) -> type[SearchIndexed]:
    """A throwaway SearchIndexed whose collection and declared indexes are injected (no Beanie)."""

    class _Model(SearchIndexed):
        _indexes: ClassVar[tuple[SearchIndex, ...]] = indexes
        _collection: ClassVar[MagicMock] = collection

        @classmethod
        def search_indexes(cls) -> tuple[SearchIndex, ...]:
            return cls._indexes

        @classmethod
        def get_pymongo_collection(cls):  # type: ignore[override]
            return cls._collection

    return _Model


class TestSyncSearchIndexes:
    async def test_missing_index_is_created(self):
        collection = _collection(existing=[])
        model = _indexed((INDEX,), collection)
        (result,) = await model.sync_search_indexes()
        assert result.status is SearchIndexSyncStatus.CREATED
        collection.create_search_index.assert_awaited_once()
        (created,) = collection.create_search_index.await_args.args
        assert isinstance(created, SearchIndexModel)
        collection.update_search_index.assert_not_awaited()

    async def test_unchanged_index_is_left_alone(self):
        collection = _collection(existing=[{"name": INDEX.name, "type": "search", "latestDefinition": INDEX.definition}])
        model = _indexed((INDEX,), collection)
        (result,) = await model.sync_search_indexes()
        assert result.status is SearchIndexSyncStatus.UNCHANGED
        collection.create_search_index.assert_not_awaited()
        collection.update_search_index.assert_not_awaited()

    async def test_changed_definition_is_updated(self):
        collection = _collection(
            existing=[{"name": INDEX.name, "type": "search", "latestDefinition": {"mappings": {"dynamic": True}}}]
        )
        model = _indexed((INDEX,), collection)
        (result,) = await model.sync_search_indexes()
        assert result.status is SearchIndexSyncStatus.UPDATED
        collection.update_search_index.assert_awaited_once_with(INDEX.name, INDEX.definition)
        collection.create_search_index.assert_not_awaited()

    async def test_type_change_is_skipped_not_rebuilt(self):
        # `type` is immutable via update_search_index, so a type mismatch must not touch the index.
        collection = _collection(
            existing=[{"name": INDEX.name, "type": "vectorSearch", "latestDefinition": INDEX.definition}]
        )
        model = _indexed((INDEX,), collection)
        (result,) = await model.sync_search_indexes()
        assert result.status is SearchIndexSyncStatus.SKIPPED_TYPE_CHANGE
        collection.create_search_index.assert_not_awaited()
        collection.update_search_index.assert_not_awaited()


class TestSyncAllSearchIndexes:
    async def test_disabled_is_a_noop(self):
        collection = _collection(existing=[])
        model = _indexed((INDEX,), collection)
        await sync_all_search_indexes([model], manage=False)
        collection.list_search_indexes.assert_not_awaited()

    async def test_non_searchindexed_models_are_skipped(self):
        # A plain class in the model list must not blow up the orchestrator.
        await sync_all_search_indexes([object, str], manage=True)

    async def test_pymongo_error_is_swallowed(self):
        # A non-Atlas target raises when the search-index command is unsupported; startup must survive.
        collection = _collection()
        collection.list_search_indexes = AsyncMock(side_effect=OperationFailure("Search not supported"))
        model = _indexed((INDEX,), collection)
        await sync_all_search_indexes([model], manage=True)  # does not raise


# ---------------------------------------------------------------------------
# Repository search — end to end against a mocked collection
# ---------------------------------------------------------------------------


class TestContributionRepositorySearch:
    async def test_pipeline_scopes_and_sorts_before_limit(self, monkeypatch):
        rows = [{"_id": None, "formula": "Fe2 O3", "project": "p", "length": 6}]
        collection = _aggregating_collection(rows)
        monkeypatch.setattr(Contribution, "get_pymongo_collection", classmethod(lambda cls: collection))

        repo = MongoDbContributionRepository(User())  # anonymous -> public-only scope
        results = await repo.search(["Fe2O3", "O3Fe2"], limit=5)

        (pipeline,) = collection.aggregate.await_args.args
        assert pipeline == [
            {"$search": {"index": "formula_autocomplete", "text": {"query": ["Fe2O3", "O3Fe2"], "path": "formula"}}},
            {"$match": {"$or": [{"is_public": True}]}},
            {"$project": {"formula": 1, "length": {"$strLenCP": "$formula"}, "project": 1}},
            {"$match": {"length": {"$gte": 5}}},
            {"$sort": {"length": 1}},  # sort precedes limit: the N genuinely-shortest formulas
            {"$limit": 5},
        ]
        assert len(results) == 1
        assert results[0].formula == "Fe2 O3"


class TestProjectRepositorySearch:
    async def test_pipeline_is_wildcard_scoped_id_only(self, monkeypatch):
        collection = _aggregating_collection([{"_id": "mp-1"}, {"_id": "mp-2"}])
        monkeypatch.setattr(Project, "get_pymongo_collection", classmethod(lambda cls: collection))

        repo = MongoDbProjectRepository(User())  # anonymous -> public+approved scope
        results = await repo.search("solar")

        (pipeline,) = collection.aggregate.await_args.args
        assert pipeline == [
            {"$search": {"index": "project-search", "text": {"query": "solar", "path": {"wildcard": "*"}}}},
            {"$match": {"$or": [{"is_public": True, "is_approved": True}]}},
            {"$project": {"_id": 1}},
        ]
        assert [p.id for p in results] == ["mp-1", "mp-2"]

    async def test_empty_scope_injects_no_match(self, monkeypatch):
        # An admin's scope is {}; _run_search must not emit a {"$match": {}} stage for it.
        collection = _aggregating_collection([{"_id": "mp-1"}])
        monkeypatch.setattr(Project, "get_pymongo_collection", classmethod(lambda cls: collection))

        repo = MongoDbProjectRepository(User())
        repo._scope = {}  # simulate the admin/empty scope
        await repo.search("solar")

        (pipeline,) = collection.aggregate.await_args.args
        assert pipeline == [
            {"$search": {"index": "project-search", "text": {"query": "solar", "path": {"wildcard": "*"}}}},
            {"$project": {"_id": 1}},
        ]
