"""Real-DB tests for the Atlas Search indexes (``domains/_shared/search_index.py`` end to end).

These exercise the parts of the search stack that a mocked collection cannot: an actual Atlas
``$search`` aggregation running against a live, built index. They cover the three seams that only
show their true behaviour against Atlas:

* **Index management** — ``sync_search_indexes`` creates the declared indexes on a fresh collection
  and, critically, is idempotent against the *server's* echoed ``latestDefinition`` (Atlas injects
  analyzer/mapping defaults; ``is_current`` must not read those as drift and trigger a rebuild).
* **Project wildcard search** — the dynamic ``*`` index matches free text across every field, and the
  read scope injected by ``_run_search`` genuinely hides documents the caller may not see.
* **Contribution formula autocomplete** — the service's element-count permutations mean a formula is
  found regardless of the order the user types the elements, the whitespace analyzer matches the
  exact formula token, and results stay scoped to the caller.

Atlas Search is asynchronous and eventually consistent: an index takes time to build after creation,
and a freshly-inserted document takes time to appear in query results even once the index is
``queryable``. Every assertion therefore goes through ``_search_eventually``, which retries until the
expected state is reached or a timeout elapses.

Requires a MongoDB Atlas deployment with Search enabled. On a plain (non-Atlas) MongoDB the
search-index commands are unsupported, so the whole module skips rather than fails — mirroring the
``mongo_client`` fixture's skip-when-unreachable behaviour.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from beanie import PydanticObjectId
from pymongo.errors import PyMongoError

from mpcontribs_api.authz import User
from mpcontribs_api.domains._shared.search_index import SearchIndexSyncStatus
from mpcontribs_api.domains.attachments.repository import MongoDbAttachmentRepository
from mpcontribs_api.domains.contributions.models import Contribution
from mpcontribs_api.domains.contributions.repository import MongoDbContributionRepository
from mpcontribs_api.domains.contributions.service import ContributionService
from mpcontribs_api.domains.downloads.service import DownloadService
from mpcontribs_api.domains.initiatives.repository import MongoDbInitiativeRepository
from mpcontribs_api.domains.projects.models import Project
from mpcontribs_api.domains.projects.repository import MongoDbProjectRepository
from mpcontribs_api.domains.projects.service import ProjectService
from mpcontribs_api.domains.structures.repository import MongoDbStructureRepository
from mpcontribs_api.domains.tables.repository import MongoDbTableRepository
from mpcontribs_api.exceptions import ValidationError

pytestmark = [pytest.mark.db, pytest.mark.asyncio(loop_scope="session")]

# How long to wait for an index to finish building, and for eventual consistency after an insert.
_BUILD_TIMEOUT_S = 180.0
_CONSISTENCY_TIMEOUT_S = 60.0
_POLL_INTERVAL_S = 2.0

ADMIN = User(username="google:admin@example.com", groups=frozenset({"admin"}))
ALICE = User(username="google:alice@example.com", groups=frozenset({"mp-team"}))
ANON = User()

ALICE_EMAIL = "google:alice@example.com"

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Service wiring — exactly as the FastAPI dependencies build them, per user
# ---------------------------------------------------------------------------


def _project_service(user: User) -> ProjectService:
    return ProjectService(
        user=user,
        projects=MongoDbProjectRepository(user),
        initiatives=MongoDbInitiativeRepository(user),
        contributions=AsyncMock(),
        structures=AsyncMock(),
        tables=AsyncMock(),
        attachments=AsyncMock(),
        downloads=AsyncMock(),
    )


def _contribution_service(client, user: User) -> ContributionService:
    return ContributionService(
        client=client,
        user=user,
        projects=MongoDbProjectRepository(user),
        contributions=MongoDbContributionRepository(user),
        structures=MongoDbStructureRepository(user),
        attachments=MongoDbAttachmentRepository(user),
        tables=MongoDbTableRepository(user),
        downloads=DownloadService(user, sqs=MagicMock(), s3=MagicMock()),
    )


# ---------------------------------------------------------------------------
# Seeding helpers (insert directly so visibility can be set for setup)
# ---------------------------------------------------------------------------


async def _insert_project(id: str, *, is_public: bool, is_approved: bool, **overrides) -> Project:
    doc = Project(
        _id=id,
        title=overrides.pop("title", id[:30]),
        authors=overrides.pop("authors", "Test Author"),
        description=overrides.pop("description", "Test description"),
        owner=overrides.pop("owner", ALICE_EMAIL),
        is_public=is_public,
        is_approved=is_approved,
        **overrides,
    )
    await doc.insert()
    return doc


async def _insert_contribution(
    *,
    project: str = "test-proj",
    identifier: str = "mp-1",
    formula: str = "Fe2O3",
    chemical_system_id: str = "Fe-O",
    is_public: bool,
    **overrides,
) -> Contribution:
    doc = Contribution(
        _id=PydanticObjectId(),
        project=project,
        material_id=identifier,
        chemical_system_id=chemical_system_id,
        formula=formula,
        data=overrides.pop("data", {"bandGap": 2.1}),
        is_public=is_public,
        **overrides,
    )
    await doc.insert()
    return doc


# ---------------------------------------------------------------------------
# Eventual-consistency polling
# ---------------------------------------------------------------------------


async def _await_queryable(model: Any, timeout: float = _BUILD_TIMEOUT_S) -> None:
    """Block until every declared search index on ``model`` reports ``queryable``.

    Atlas builds indexes asynchronously (``PENDING`` → ``BUILDING`` → ``READY``); querying one before
    it is ``queryable`` returns nothing rather than erroring, which would make tests silently flaky.
    """
    collection = model.get_pymongo_collection()
    wanted = {index.name for index in model.search_indexes()}
    deadline = time.monotonic() + timeout
    while True:
        live = {doc["name"]: doc async for doc in await collection.list_search_indexes()}
        if all(live.get(name, {}).get("queryable") for name in wanted):
            return
        if time.monotonic() >= deadline:
            missing = {name: live.get(name, {}).get("status") for name in wanted}
            raise TimeoutError(f"{model.__name__} search indexes not queryable within {timeout}s: {missing}")
        await asyncio.sleep(_POLL_INTERVAL_S)


async def _search_eventually(
    run: Callable[[], Awaitable[T]],
    predicate: Callable[[T], bool],
    timeout: float = _CONSISTENCY_TIMEOUT_S,
) -> T:
    """Retry ``run`` until ``predicate`` accepts its result or ``timeout`` elapses.

    A just-inserted document is not immediately visible to ``$search`` even on a queryable index, so a
    single call would race the index. The last result is returned on timeout so the caller's assertion
    fails with the real (wrong) value rather than an opaque timeout.
    """
    deadline = time.monotonic() + timeout
    result = await run()
    while not predicate(result) and time.monotonic() < deadline:
        await asyncio.sleep(_POLL_INTERVAL_S)
        result = await run()
    return result


def _ids(items) -> set[str]:
    return {str(item.id) for item in items}


# ---------------------------------------------------------------------------
# Module fixture: create the indexes once, then wait for them to build
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="module")
async def search_indexes(db):
    """Sync both models' Atlas Search indexes on the (freshly-dropped) collections and wait for them.

    Module-scoped: index creation and the multi-minute build happen once for the whole module. The
    per-test ``clean_*`` fixtures wipe *documents* between tests but leave the indexes in place.

    Atlas' ``createSearchIndexes`` requires the target namespace to already exist. The session ``db``
    fixture drops these collections and ``init_beanie`` does not physically recreate them until the
    first write, so create them explicitly here first — otherwise the sync fails with
    ``NamespaceNotFound`` and (mis)reads as "search unavailable".
    """
    existing = await db.list_collection_names()
    for model in (Project, Contribution):
        name = model.get_pymongo_collection().name
        if name not in existing:
            await db.create_collection(name)
    try:
        await Project.sync_search_indexes()
        await Contribution.sync_search_indexes()
    except PyMongoError as exc:
        pytest.skip(f"Atlas Search not available on this deployment: {exc}")
    await _await_queryable(Project)
    await _await_queryable(Contribution)
    yield


# ---------------------------------------------------------------------------
# Index management — sync_search_indexes against real Atlas
# ---------------------------------------------------------------------------


class TestSyncSearchIndexes:
    async def test_declared_indexes_exist_after_sync(self, db, search_indexes):
        live = {doc["name"] async for doc in await Contribution.get_pymongo_collection().list_search_indexes()}
        assert "formula_autocomplete" in live
        live_projects = {doc["name"] async for doc in await Project.get_pymongo_collection().list_search_indexes()}
        assert "project-search" in live_projects

    async def test_resync_is_unchanged_not_a_rebuild(self, db, search_indexes):
        # The core value of is_current/_is_subset: Atlas echoes the definition back with server-injected
        # defaults (normalized analyzers, expanded dynamic mappings). A second sync must read those as
        # equal and report UNCHANGED — otherwise every startup would trigger an expensive rebuild.
        for model in (Project, Contribution):
            results = await model.sync_search_indexes()
            assert results, f"{model.__name__} declared no indexes"
            assert all(r.status is SearchIndexSyncStatus.UNCHANGED for r in results), results


# ---------------------------------------------------------------------------
# Project wildcard search — dynamic index + read-scope injection
#
# The text and scope behaviours belong to the index, so they are driven through the repository
# directly. The service adds the empty-query guard and forwards ``limit`` to the repo, so the limit
# cap is asserted through the service to cover that hand-off end to end.
# ---------------------------------------------------------------------------


class TestProjectSearch:
    async def test_wildcard_matches_indexed_free_text(self, db, search_indexes):
        # A dynamic index covers every field; a term in the description alone is enough to match.
        await _insert_project(
            "solar-photovoltaics",
            is_public=True,
            is_approved=True,
            title="Perovskite study",
            description="High-efficiency photovoltaics for solar energy conversion",
        )
        results = await _search_eventually(
            lambda: MongoDbProjectRepository(ADMIN).search("photovoltaics"),
            lambda r: "solar-photovoltaics" in _ids(r),
        )
        assert "solar-photovoltaics" in _ids(results)

    async def test_scope_hides_private_project_from_anonymous(self, db, search_indexes):
        # Same matching term on a private project: the $match scope in _run_search must exclude it for
        # an anonymous caller while an admin (empty scope) still sees it.
        await _insert_project(
            "hidden-catalysis",
            is_public=False,
            is_approved=False,
            description="secret catalysis research on novel electrocatalysts",
        )
        admin_hit = await _search_eventually(
            lambda: MongoDbProjectRepository(ADMIN).search("electrocatalysts"),
            lambda r: "hidden-catalysis" in _ids(r),
        )
        assert "hidden-catalysis" in _ids(admin_hit)

        # The admin already saw it, so the index is populated; the anon result is a real exclusion.
        anon_result = await MongoDbProjectRepository(ANON).search("electrocatalysts")
        assert "hidden-catalysis" not in _ids(anon_result)

    async def test_group_member_sees_granted_private_project(self, db, search_indexes):
        # A private, non-owner project granted to ALICE's group: the token "mp-team" maps (legacy
        # shorthand) to a grant on project id "mp-team". ALICE sees it via the Granted scope clause;
        # an anonymous caller, held to public+approved, does not.
        await _insert_project(
            "mp-team",
            is_public=False,
            is_approved=False,
            owner="google:bob@example.com",
            description="granted-only magnetometry of layered superconductors",
        )
        alice_hit = await _search_eventually(
            lambda: MongoDbProjectRepository(ALICE).search("magnetometry"),
            lambda r: "mp-team" in _ids(r),
        )
        assert "mp-team" in _ids(alice_hit)

        # ALICE already surfaced it, so the index is populated; the anon miss is a real exclusion.
        anon_result = await MongoDbProjectRepository(ANON).search("magnetometry")
        assert "mp-team" not in _ids(anon_result)

    async def test_limit_caps_the_result_count(self, db, search_indexes):
        # Driven through the service to prove it forwards ``limit`` to the repo (not just the repo's
        # own $limit stage).
        for i in range(5):
            await _insert_project(
                f"limit-thermoelectrics-{i}",
                is_public=True,
                is_approved=True,
                description="thermoelectrics figure of merit survey",
            )
        results = await _search_eventually(
            lambda: _project_service(ADMIN).search("thermoelectrics", limit=2),
            lambda r: len(r) >= 2,
        )
        assert len(results) == 2

    async def test_empty_query_is_rejected(self, db, search_indexes):
        # Guarded in the service before any Atlas call.
        with pytest.raises(ValidationError):
            await _project_service(ADMIN).search("")


# ---------------------------------------------------------------------------
# Contribution formula autocomplete — permutations + whitespace analyzer + scope
# ---------------------------------------------------------------------------


class TestContributionFormulaSearch:
    async def test_formula_round_trips(self, db, mongo_client, search_indexes):
        contribution = await _insert_contribution(formula="Fe2O3", is_public=True)
        results = await _search_eventually(
            lambda: _contribution_service(mongo_client, ADMIN).search("Fe2O3"),
            lambda r: str(contribution.id) in _ids(r),
        )
        assert str(contribution.id) in _ids(results)
        assert all(item.formula == "Fe2O3" for item in results)

    async def test_element_order_is_independent(self, db, mongo_client, search_indexes):
        # The service expands the query into element-count permutations, so a user who types the
        # elements in a different order than they are stored ("O3Fe2" vs the stored "Fe2O3") still
        # matches. This is the whole reason the service builds permutations rather than a single token.
        contribution = await _insert_contribution(formula="Fe2O3", identifier="order-independent", is_public=True)
        results = await _search_eventually(
            lambda: _contribution_service(mongo_client, ADMIN).search("O3Fe2"),
            lambda r: str(contribution.id) in _ids(r),
        )
        assert str(contribution.id) in _ids(results)

    async def test_scope_hides_private_contribution_from_anonymous(self, db, mongo_client, search_indexes):
        contribution = await _insert_contribution(formula="Fe2O3", identifier="private-formula", is_public=False)
        admin_hit = await _search_eventually(
            lambda: _contribution_service(mongo_client, ADMIN).search("Fe2O3"),
            lambda r: str(contribution.id) in _ids(r),
        )
        assert str(contribution.id) in _ids(admin_hit)

        anon_result = await _contribution_service(mongo_client, ANON).search("Fe2O3")
        assert str(contribution.id) not in _ids(anon_result)

    async def test_group_member_sees_granted_private_contribution(self, db, mongo_client, search_indexes):
        # Contribution scope is grant-only (no owner clause): ALICE's "mp-team" group grants visibility
        # of contributions whose ``project`` is "mp-team". An anonymous caller sees only public rows.
        contribution = await _insert_contribution(
            project="mp-team", formula="Fe2O3", identifier="granted-formula", is_public=False
        )
        alice_hit = await _search_eventually(
            lambda: _contribution_service(mongo_client, ALICE).search("Fe2O3"),
            lambda r: str(contribution.id) in _ids(r),
        )
        assert str(contribution.id) in _ids(alice_hit)

        anon_result = await _contribution_service(mongo_client, ANON).search("Fe2O3")
        assert str(contribution.id) not in _ids(anon_result)

    async def test_non_matching_formula_returns_nothing(self, db, mongo_client, search_indexes):
        # The whitespace analyzer keys on the exact formula token, so a different compound must not
        # surface. Insert Fe2O3, then confirm SiO2 (a valid but distinct formula) finds no Fe2O3 row.
        await _insert_contribution(formula="Fe2O3", is_public=True)
        # Give the index a beat to absorb the insert, then a distinct-formula search must be empty.
        await _search_eventually(
            lambda: _contribution_service(mongo_client, ADMIN).search("Fe2O3"),
            lambda r: len(r) >= 1,
        )
        result = await _contribution_service(mongo_client, ADMIN).search("SiO2")
        assert result == []

    async def test_invalid_formula_is_rejected(self, db, mongo_client, search_indexes):
        # A query that is not a parseable composition never reaches Atlas.
        with pytest.raises(ValidationError):
            await _contribution_service(mongo_client, ADMIN).search("not-a-formula!!")
