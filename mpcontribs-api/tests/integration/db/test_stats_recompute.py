"""End-to-end tests for the Project.stats/columns recompute driven by contribution writes.

Every contribution insert/delete recomputes the owning project's rollup (see
``ContributionService.update_project``). These tests drive the real service against the dev DB and
assert the project's persisted ``stats``/``columns`` after each step of the lifecycle:

  create project -> empty
  insert 1 contribution with two tables (and data) -> filled
  delete it -> empty
  insert 1 contribution with no components -> filled from data only
  delete it -> empty
  insert two contributions whose data overlaps and diverges -> merged columns (a new column appears)

The component-count step uses tables only. Structures are now S3-versioned and are created/linked by
the transform worker (not inline on a contribution insert — see ContributionService._do_insert_group),
so a structure submitted on a synchronous insert is not linked and would never be counted. Attachments
are likewise not wired by the insert path. Structure/table/attachment counting is symmetric in the
aggregation, so exercising it via tables still covers the component path.
"""

import polars as pl
import pytest

from mpcontribs_api.authz import User
from mpcontribs_api.domains.contributions.models import ContributionFilter, ContributionIn
from mpcontribs_api.domains.contributions.repository import MongoDbContributionRepository
from mpcontribs_api.domains.contributions.service import ContributionService
from mpcontribs_api.domains.attachments.repository import MongoDbAttachmentRepository
from mpcontribs_api.domains.projects.models import Column, Project, ProjectIn, Stats
from mpcontribs_api.domains.projects.repository import MongoDbProjectRepository
from mpcontribs_api.domains.structures.repository import MongoDbStructureRepository
from mpcontribs_api.domains.tables.models import TableIn
from mpcontribs_api.domains.tables.repository import MongoDbTableRepository

pytestmark = [pytest.mark.db, pytest.mark.asyncio(loop_scope="session")]


ADMIN = User(username="google:admin@example.com", groups=frozenset({"admin"}))
EMPTY_STATS = Stats(columns=0, contributions=0, tables=0, structures=0, attachments=0, size=0.0)
PID = "stats-proj"


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _service(client) -> ContributionService:
    """A ContributionService wired exactly like the FastAPI dependency, for ADMIN."""
    return ContributionService(
        client=client,
        user=ADMIN,
        projects=MongoDbProjectRepository(ADMIN),
        contributions=MongoDbContributionRepository(ADMIN),
        structures=MongoDbStructureRepository(ADMIN),
        attachments=MongoDbAttachmentRepository(ADMIN),
        tables=MongoDbTableRepository(ADMIN),
    )


async def _make_project() -> Project:
    project_in = ProjectIn(
        title="Stats Project",
        authors="Test Author",
        description="Recompute lifecycle fixture",
        owner="google:admin@example.com",
    )
    return await MongoDbProjectRepository(ADMIN).upsert_one(Project.from_input_model(project_in, id=PID))


def _table(value: float) -> TableIn:
    """A valid table; distinct ``data`` yields a distinct md5."""
    return TableIn(
        name="table",
        attrs={"title": "t", "labels": {"index": "x", "value": "y", "variable": "z"}},
        data=pl.DataFrame({"col": [value]}),
    )


def _contrib_in(identifier: str, data: dict, **overrides) -> ContributionIn:
    # ``identifier`` is a human label; distill its letters into a valid ``mp-<letters>`` material_id
    # (<=8 letters) so each contribution's identity tuple differs.
    letters = "".join(c for c in identifier.lower() if c.isalpha())[:8] or "a"
    return ContributionIn(
        project=PID, material_id=f"mp-{letters}", chemical_system_id="Fe-O", formula="Fe2O3", data=data, **overrides
    )


# ---------------------------------------------------------------------------
# Assertion helpers
# ---------------------------------------------------------------------------


async def _project() -> Project:
    """Re-read the full project document from the DB."""
    project = await Project.find_one(Project.id == PID)
    assert project is not None
    return project


async def _assert_empty() -> None:
    project = await _project()
    assert project.stats == EMPTY_STATS
    assert project.columns == []


def _columns_by_path(project: Project) -> dict[str, Column]:
    return {c.path: c for c in project.columns}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestStatsRecomputeLifecycle:
    async def test_new_project_starts_empty(self, db, mongo_client):
        await _make_project()
        await _assert_empty()

    async def test_full_lifecycle(self, db, mongo_client):
        svc = _service(mongo_client)
        await _make_project()
        await _assert_empty()

        # --- insert one contribution with two tables (+ data) ---
        # Structures are not wired by the synchronous insert path (worker-linked, S3-versioned), so the
        # component-count step uses tables; structures stay at 0.
        summary = await svc.insert_many(
            [
                _contrib_in(
                    "with-components",
                    data={"bandGap": 2.1, "energy": -5.0},
                    tables=[_table(1.0), _table(2.0)],
                )
            ]
        )
        assert summary.failed == []
        assert len(summary.succeeded) == 1

        project = await _project()
        assert project.stats.contributions == 1
        assert project.stats.structures == 0
        assert project.stats.tables == 2
        assert project.stats.attachments == 0
        assert project.stats.size > 0
        cols = _columns_by_path(project)
        # Data keys are coerced to camelCase on write, so derived columns use the camelCase form.
        assert set(cols) == {"bandGap", "energy"}
        assert project.stats.columns == 2
        assert (cols["bandGap"].min, cols["bandGap"].max) == (2.1, 2.1)
        assert (cols["energy"].min, cols["energy"].max) == (-5.0, -5.0)

        # --- remove it -> back to empty ---
        # NOTE: svc.delete_many() cannot delete a contribution that references a real table
        # component: its cascade re-reads the contribution through ContributionFilter, whose nested
        # component sub-filters make Beanie fetch the linked components, and the fetched Table.data
        # frame fails to round-trip (Table.data is a PolarsFrame that pymongo stores as bare column
        # lists which _coerce_frame rejects on read). That is a pre-existing bug in the tables domain,
        # unrelated to the stats recompute. (Structure.lattice.matrix used to hit the same bug but is
        # now a plain nested-list type that round-trips.) To still assert the removal recompute, drop
        # the docs directly and recompute; the no-components case below covers delete() end-to-end.
        await db["contributions"].delete_many({"project": PID})
        for coll in ("structures", "tables"):
            await db[coll].delete_many({})
        await svc.update_project([PID])
        await _assert_empty()

        # --- insert one contribution with no components ---
        summary = await svc.insert_many([_contrib_in("no-components", data={"bandGap": 3.0})])
        assert summary.failed == []
        project = await _project()
        assert project.stats.contributions == 1
        assert project.stats.structures == 0
        assert project.stats.tables == 0
        assert project.stats.size > 0
        cols = _columns_by_path(project)
        assert set(cols) == {"bandGap"}
        assert (cols["bandGap"].min, cols["bandGap"].max) == (3.0, 3.0)

        # --- remove it -> empty again ---
        deleted = await svc.delete_many(ContributionFilter(id=summary.succeeded[0].id))
        assert deleted.num_deleted == 1
        await _assert_empty()

        # --- add two contributions whose data overlaps ("shared") and diverges ("b" is new) ---
        await svc.insert_many([_contrib_in("c-one", data={"a": 1.0, "shared": 5.0})])
        project = await _project()
        assert project.stats.contributions == 1
        assert set(_columns_by_path(project)) == {"a", "shared"}

        await svc.insert_many([_contrib_in("c-two", data={"shared": 9.0, "b": 2.0})])
        project = await _project()
        assert project.stats.contributions == 2
        cols = _columns_by_path(project)
        # The second contribution introduces a brand-new column and widens a shared one.
        assert set(cols) == {"a", "shared", "b"}
        assert project.stats.columns == 3
        assert (cols["shared"].min, cols["shared"].max) == (5.0, 9.0)
        assert (cols["a"].min, cols["a"].max) == (1.0, 1.0)
        assert (cols["b"].min, cols["b"].max) == (2.0, 2.0)
