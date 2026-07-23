"""End-to-end tests for the Project.stats/columns recompute driven by contribution writes.

Every contribution insert/delete recomputes the owning project's rollup (see
``ContributionService.update_project``). These tests drive the real service against the dev DB and
assert the project's persisted ``stats``/``columns`` after each step of the lifecycle:

  create project -> empty
  insert 1 contribution with two structures + two tables (and data) -> filled
  delete it -> empty
  insert 1 contribution with no components -> filled from data only
  delete it -> empty
  insert two contributions whose data overlaps and diverges -> merged columns (a new column appears)

Attachments are intentionally excluded from the "two of each component" step: the contribution
insert path only wires structures and tables (see ContributionService._do_insert_group), so
attachments submitted on a contribution would be dropped and never counted. Structure/table/
attachment counting is symmetric in the aggregation, so this still exercises the component path.
"""

import polars as pl
import pytest
from beanie import PydanticObjectId
from pymatgen.core import Element

from mpcontribs_api.authz import User
from mpcontribs_api.domains.contributions.models import ContributionFilter, ContributionIn
from mpcontribs_api.domains.contributions.repository import MongoDbContributionRepository
from mpcontribs_api.domains.contributions.service import ContributionService
from mpcontribs_api.domains.attachments.repository import MongoDbAttachmentRepository
from mpcontribs_api.domains.projects.models import Column, Project, ProjectIn, Stats
from mpcontribs_api.domains.projects.repository import MongoDbProjectRepository
from mpcontribs_api.domains.structures.models import Lattice, Site, SiteProperties, Species, StructureIn
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


async def _make_project(unique_identifiers: bool = True) -> Project:
    project_in = ProjectIn(
        title="Stats Project",
        authors="Test Author",
        description="Recompute lifecycle fixture",
        owner="google:admin@example.com",
        unique_identifiers=unique_identifiers,
    )
    return await MongoDbProjectRepository(ADMIN).insert_project(PID, project_in)


def _structure(charge: float | None) -> StructureIn:
    """A valid structure; ``charge`` is a hash field, so varying it yields a distinct md5."""
    return StructureIn(
        name="struct",
        lattice=Lattice(
            matrix=pl.DataFrame([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]),
            pbc=[True, True, True],
            a=1.0, b=1.0, c=1.0,
            alpha=90.0, beta=90.0, gamma=90.0,
            volume=1.0,
        ),
        sites=[
            Site(
                species=[Species(element=Element("Fe"), occu=1)],
                abc=[0.0, 0.0, 0.0],
                properties=SiteProperties(magmom=0.0),
                label="Fe",
                xyz=[0.0, 0.0, 0.0],
            )
        ],
        charge=charge,
        cif="",
    )


def _table(value: float) -> TableIn:
    """A valid table; distinct ``data`` yields a distinct md5."""
    return TableIn(
        name="table",
        attrs={"title": "t", "labels": {"index": "x", "value": "y", "variable": "z"}},
        data=pl.DataFrame({"col": [value]}),
    )


def _contrib_in(identifier: str, data: dict, **overrides) -> ContributionIn:
    return ContributionIn(project=PID, identifier=identifier, formula="Fe2O3", data=data, **overrides)


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

        # --- insert one contribution with two structures + two tables (+ data) ---
        summary = await svc.insert_contributions(
            [
                _contrib_in(
                    "with-components",
                    data={"band_gap": 2.1, "energy": -5.0},
                    structures=[_structure(charge=None), _structure(charge=1.0)],
                    tables=[_table(1.0), _table(2.0)],
                )
            ]
        )
        assert summary.failed == []
        assert len(summary.succeeded) == 1

        project = await _project()
        assert project.stats.contributions == 1
        assert project.stats.structures == 2
        assert project.stats.tables == 2
        assert project.stats.attachments == 0
        assert project.stats.size > 0
        cols = _columns_by_path(project)
        assert set(cols) == {"band_gap", "energy"}
        assert project.stats.columns == 2
        assert (cols["band_gap"].min, cols["band_gap"].max) == (2.1, 2.1)
        assert (cols["energy"].min, cols["energy"].max) == (-5.0, -5.0)

        # --- remove it -> back to empty ---
        # NOTE: svc.delete_contributions() cannot delete a contribution that references real
        # structure/table components: its cascade re-reads the contribution through ContributionFilter,
        # whose nested component sub-filters make Beanie fetch the linked components, and the fetched
        # frame content (e.g. Lattice.matrix) fails to round-trip (Structure/Table don't register
        # FRAME_BSON_ENCODERS, so it is stored as a bare list _coerce_frame rejects). That is a
        # pre-existing bug unrelated to the stats recompute. To still assert the removal recompute,
        # drop the docs directly and recompute; the no-components case below covers delete() end-to-end.
        await db["contributions"].delete_many({"project": PID})
        for coll in ("structures", "tables"):
            await db[coll].delete_many({})
        await svc.update_project([PID])
        await _assert_empty()

        # --- insert one contribution with no components ---
        summary = await svc.insert_contributions([_contrib_in("no-components", data={"band_gap": 3.0})])
        assert summary.failed == []
        project = await _project()
        assert project.stats.contributions == 1
        assert project.stats.structures == 0
        assert project.stats.tables == 0
        assert project.stats.size > 0
        cols = _columns_by_path(project)
        assert set(cols) == {"band_gap"}
        assert (cols["band_gap"].min, cols["band_gap"].max) == (3.0, 3.0)

        # --- remove it -> empty again ---
        deleted = await svc.delete_contributions(ContributionFilter(id=summary.succeeded[0].id))
        assert deleted.num_deleted == 1
        await _assert_empty()

        # --- add two contributions whose data overlaps ("shared") and diverges ("b" is new) ---
        await svc.insert_contributions([_contrib_in("c-one", data={"a": 1.0, "shared": 5.0})])
        project = await _project()
        assert project.stats.contributions == 1
        assert set(_columns_by_path(project)) == {"a", "shared"}

        await svc.insert_contributions([_contrib_in("c-two", data={"shared": 9.0, "b": 2.0})])
        project = await _project()
        assert project.stats.contributions == 2
        cols = _columns_by_path(project)
        # The second contribution introduces a brand-new column and widens a shared one.
        assert set(cols) == {"a", "shared", "b"}
        assert project.stats.columns == 3
        assert (cols["shared"].min, cols["shared"].max) == (5.0, 9.0)
        assert (cols["a"].min, cols["a"].max) == (1.0, 1.0)
        assert (cols["b"].min, cols["b"].max) == (2.0, 2.0)
