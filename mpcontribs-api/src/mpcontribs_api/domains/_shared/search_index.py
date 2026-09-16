from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING, Any

import structlog
from pydantic import BaseModel
from pymongo.errors import PyMongoError
from pymongo.operations import SearchIndexModel

if TYPE_CHECKING:
    from pymongo.asynchronous.collection import AsyncCollection

logger = structlog.get_logger(__name__)

# The ``$search`` wildcard path: match the query against every field a (dynamic) index covers,
# each through its own analyzer.
WILDCARD_PATH: Mapping[str, Any] = {"wildcard": "*"}


@dataclass(frozen=True)
class SearchQuery:
    """A composable Atlas ``$search`` aggregation, built fluently and rendered to a pipeline.

    Owns the raw Mongo shape so repositories never author ``$search`` / ``$match`` dicts by hand -
    the way Beanie owns ``find``. Start one with :meth:`SearchIndex.text`, chain the post-``$search``
    stages, and hand it to ``MongoDbRepository._run_search``. Instances are immutable; each builder
    method returns a new query.

    Attributes:
        index_name: the Atlas Search index the ``$search`` stage targets
        operator: the ``$search`` operator body (e.g. ``{"text": {...}}``)
        stages: ordered post-``$search`` pipeline stages (project/match/sort/limit)
    """

    index_name: str
    operator: Mapping[str, Any]
    stages: tuple[Mapping[str, Any], ...] = ()

    def _add(self, stage: Mapping[str, Any]) -> SearchQuery:
        return replace(self, stages=(*self.stages, stage))

    def project(self, projection: Mapping[str, Any]) -> SearchQuery:
        """Append a ``$project`` stage."""
        return self._add({"$project": dict(projection)})

    def match(self, filter: Mapping[str, Any]) -> SearchQuery:
        """Append a ``$match`` stage."""
        return self._add({"$match": dict(filter)})

    def sort(self, sort: Mapping[str, Any]) -> SearchQuery:
        """Append a ``$sort`` stage."""
        return self._add({"$sort": dict(sort)})

    def limit(self, limit: int) -> SearchQuery:
        """Append a ``$limit`` stage."""
        return self._add({"$limit": limit})

    def to_pipeline(self) -> list[dict[str, Any]]:
        """Render the aggregation pipeline: the ``$search`` stage followed by the chained stages.

        ``$search`` is always the first stage - Atlas requires it.

        Returns:
            list[dict[str, Any]]: the ``$search`` stage followed by the builder's stages in order
        """
        pipeline: list[dict[str, Any]] = [{"$search": {"index": self.index_name, **self.operator}}]
        pipeline.extend(dict(stage) for stage in self.stages)
        return pipeline


@dataclass(frozen=True)
class SearchIndex:
    """A single Atlas Search index: its definition and the entry point for querying it.

    ``pymongo.SearchIndexModel`` does not keep its parameters accessible, so this dataclass holds
    them for both index management (:meth:`to_pymongo`, :meth:`is_current`) and query construction
    (:meth:`text`).
    """

    name: str
    type: str
    definition: dict[str, Any]

    def to_pymongo(self) -> SearchIndexModel:
        return SearchIndexModel(name=self.name, type=self.type, definition=self.definition)

    def text(self, query: Any, path: str | Mapping[str, Any]) -> SearchQuery:
        """Begin a ``text`` ``$search`` query on this index.

        Args:
            query: the term(s) to search for (a string, or a list of terms matched as OR)
            path: a field name (e.g. ``"formula"``) or :data:`WILDCARD_PATH` to search every field a
                dynamic index covers

        Returns:
            SearchQuery: a query seeded with this index and the ``text`` operator, ready to chain
        """
        return SearchQuery(index_name=self.name, operator={"text": {"query": query, "path": path}})

    def is_current(self, existing: Mapping[str, Any]) -> bool:
        """True when the live Atlas index ``existing`` already reflects this definition.

        ``existing`` is one document from ``list_search_indexes()``. This declaration's ``definition``
        is compared as a subset of the server's ``latestDefinition`` so server-injected defaults
        (analyzer normalization, expanded dynamic mappings) don't read as drift and trigger a
        needless - and expensive - rebuild on every startup. Trade-off: a field removed from
        ``definition`` is not detected as drift here.
        """
        return _is_subset(self.definition, existing.get("latestDefinition", {}))


def _is_subset(desired: Any, actual: Any) -> bool:
    """Recursively test whether ``desired`` is contained in ``actual`` (dicts by key, lists by position)."""
    if isinstance(desired, Mapping):
        return isinstance(actual, Mapping) and all(
            key in actual and _is_subset(value, actual[key]) for key, value in desired.items()
        )
    if isinstance(desired, list):
        return (
            isinstance(actual, list)
            and len(desired) == len(actual)
            and all(_is_subset(d, a) for d, a in zip(desired, actual, strict=False))
        )
    return desired == actual


class SearchIndexSyncStatus(StrEnum):
    """Outcome of reconciling one declared index with Atlas."""

    CREATED = "created"
    UPDATED = "updated"
    UNCHANGED = "unchanged"
    SKIPPED_TYPE_CHANGE = "skipped_type_change"


@dataclass(frozen=True)
class SearchIndexSyncResult:
    """What :meth:`SearchIndexed.sync_search_indexes` did for a single index."""

    model: str
    index: str
    status: SearchIndexSyncStatus


class SearchIndexed(BaseModel, ABC):
    """Mixin for Beanie ``Document`` subclasses that declare and manage Atlas Search indexes.

    A model lists its indexes in :meth:`search_indexes`; the mixin then both manages them in Atlas
    (:meth:`sync_search_indexes`) and hands the query side a typed :class:`SearchIndex`
    (:meth:`get_search_index`) so pipelines are built through :class:`SearchQuery` rather
    than raw Mongo.

    Use :meth:`_path` inside ``search_indexes`` to validate field paths against the
    model and prevent drift.
    """

    if TYPE_CHECKING:
        # Provided by the Beanie ``Document`` this mixin is always combined with in a concrete class.
        @classmethod
        def get_pymongo_collection(cls) -> AsyncCollection: ...

    @classmethod
    @abstractmethod
    def search_indexes(cls) -> tuple[SearchIndex, ...]:
        """Declare this model's search indexes."""
        ...

    @classmethod
    def _path(cls, *parts: str) -> str:
        """Validate a field path against the model at call time."""
        head, *rest = parts
        if head not in cls.model_fields:
            raise KeyError(f"{cls.__name__} has no field {head!r}")
        info = cls.model_fields[head]
        return ".".join((info.alias or head, *rest))

    @classmethod
    def get_search_index(cls, name: str) -> SearchIndex:
        """Return the declared :class:`SearchIndex` whose name is ``name`` (repos pass the enum member)."""
        for index in cls.search_indexes():
            if index.name == name:
                return index
        raise KeyError(f"{cls.__name__} declares no search index named {name!r}")

    @classmethod
    async def sync_search_indexes(cls) -> list[SearchIndexSyncResult]:
        """Idempotently reconcile this model's declared indexes with Atlas.

        Creates missing indexes and updates changed ones, but never waits for
        Atlas's asynchronous ``PENDING → READY`` build. ``type`` is immutable via
        ``update_search_index``, so a same-named index of a different type is logged and skipped
        rather than rebuilt.

        Returns:
            list[SearchIndexSyncResult]: one result per declared index
        """
        collection = cls.get_pymongo_collection()
        existing = {doc["name"]: doc async for doc in await collection.list_search_indexes()}

        results: list[SearchIndexSyncResult] = []
        for spec in cls.search_indexes():
            current = existing.get(spec.name)
            if current is None:
                await collection.create_search_index(spec.to_pymongo())
                status = SearchIndexSyncStatus.CREATED
            elif current.get("type", "search") != spec.type:
                logger.warning(
                    "search_index_type_change_skipped",
                    model=cls.__name__,
                    index=spec.name,
                    existing_type=current.get("type"),
                    declared_type=spec.type,
                )
                status = SearchIndexSyncStatus.SKIPPED_TYPE_CHANGE
            elif spec.is_current(current):
                status = SearchIndexSyncStatus.UNCHANGED
            else:
                await collection.update_search_index(spec.name, spec.definition)
                status = SearchIndexSyncStatus.UPDATED
            results.append(SearchIndexSyncResult(model=cls.__name__, index=spec.name, status=status))
        return results


async def sync_all_search_indexes(document_models: Iterable[type], *, manage: bool) -> None:
    """Sync every :class:`SearchIndexed` model in ``document_models`` with Atlas.

    Non-fatal and non-blocking: when ``manage`` is False it is a logged no-op, and a ``PyMongoError``
    from any one model (e.g. the target is not an Atlas cluster, so the search-index commands are
    unsupported) is caught and logged so startup always proceeds.

    Args:
        document_models: the app's document models (non-``SearchIndexed`` ones are skipped)
        manage: whether index management is enabled (``mongo.manage_search_indexes``)
    """
    if not manage:
        logger.info("search_index_sync_disabled")
        return
    for model in document_models:
        if not (isinstance(model, type) and issubclass(model, SearchIndexed)):
            continue
        try:
            results = await model.sync_search_indexes()
        except PyMongoError as err:
            logger.warning("search_index_sync_failed", model=model.__name__, error=str(err))
            continue
        for result in results:
            logger.info("search_index_sync", model=result.model, index=result.index, status=result.status)
