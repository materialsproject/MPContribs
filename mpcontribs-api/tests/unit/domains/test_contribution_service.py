"""Unit tests for ContributionService.

All database access is replaced with AsyncMock repositories so no MongoDB
connection is needed.  These tests verify:
  - _insert_components: slice bookkeeping and delegation to component repos
  - insert_contributions: Link wiring and bulk-insert delegation
  - upsert_contributions: guard against components, insert vs update branching
"""

from unittest.mock import AsyncMock, MagicMock

import polars as pl
import pytest
from beanie import PydanticObjectId
from pymatgen.core import Element

from mpcontribs_api.domains.attachments.models import Attachment, AttachmentIn
from mpcontribs_api.domains.contributions.models import Contribution, ContributionIn
from mpcontribs_api.domains.contributions.service import ContributionService
from mpcontribs_api.domains.structures.models import (
    Lattice,
    Site,
    SiteProperties,
    Species,
    Structure,
    StructureIn,
)
from mpcontribs_api.domains.tables.models import Attributes, Labels, Table, TableIn
from mpcontribs_api.exceptions import ValidationError

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _oid() -> PydanticObjectId:
    return PydanticObjectId()


def _attachment_in(**overrides) -> AttachmentIn:
    defaults = {
        "_id": _oid(),
        "name": "data.gz",
        "md5": "a" * 32,
        "mime": "application/gzip",
        "content": 0,
    }
    defaults.update(overrides)
    return AttachmentIn(**defaults)


def _table_in(**overrides) -> TableIn:
    defaults = {
        "_id": _oid(),
        "name": "test-table",
        "md5": "b" * 32,
        "attrs": Attributes(title="T", labels=Labels(index="x", value="y", variable="z")),
        "total_data_rows": 1,
        "data": pl.DataFrame({"col": [1.0]}),
    }
    defaults.update(overrides)
    return TableIn(**defaults)


def _structure_in(**overrides) -> StructureIn:
    defaults = {
        "_id": _oid(),
        "name": "test-struct",
        "md5": "c" * 32,
        "lattice": Lattice(
            matrix=pl.DataFrame([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]),
            pbc=[True, True, True],
            a=1.0, b=1.0, c=1.0,
            alpha=90.0, beta=90.0, gamma=90.0,
            volume=1.0,
        ),
        "sites": [
            Site(
                species=[Species(element=Element("Fe"), occu=1)],
                abc=[0.0, 0.0, 0.0],
                properties=SiteProperties(magmom=0.0),
                label="Fe",
                xyz=[0.0, 0.0, 0.0],
            )
        ],
        "charge": None,
        "cif": "",
    }
    defaults.update(overrides)
    return StructureIn(**defaults)


def _contrib_in(project="proj", identifier="mp-1", formula="Fe2O3", **kwargs) -> ContributionIn:
    return ContributionIn(
        _id=_oid(),
        project=project,
        identifier=identifier,
        formula=formula,
        data={},
        **kwargs,
    )


def _make_service(
    contributions=None,
    structures=None,
    tables=None,
    attachments=None,
) -> tuple[ContributionService, AsyncMock, AsyncMock, AsyncMock, AsyncMock]:
    contrib_repo = contributions or AsyncMock()
    struct_repo = structures or AsyncMock()
    table_repo = tables or AsyncMock()
    attach_repo = attachments or AsyncMock()
    svc = ContributionService(
        contributions=contrib_repo,
        structures=struct_repo,
        tables=table_repo,
        attachments=attach_repo,
    )
    return svc, contrib_repo, struct_repo, table_repo, attach_repo


def _fake_structure() -> Structure:
    s = MagicMock(spec=Structure)
    s.id = _oid()
    return s


def _fake_table() -> Table:
    t = MagicMock(spec=Table)
    t.id = _oid()
    return t


def _fake_attachment() -> Attachment:
    a = MagicMock(spec=Attachment)
    a.id = _oid()
    return a


# ---------------------------------------------------------------------------
# _insert_components
# ---------------------------------------------------------------------------


class TestInsertComponents:
    async def test_empty_batch_calls_repos_with_empty_lists(self):
        svc, _, struct_repo, table_repo, attach_repo = _make_service()
        struct_repo.insert_structures.return_value = []
        table_repo.insert_tables.return_value = []
        attach_repo.insert_attachments.return_value = []

        structures, tables, attachments, ss, ts, ats = await svc._insert_components([])

        struct_repo.insert_structures.assert_called_once_with([])
        table_repo.insert_tables.assert_called_once_with([])
        attach_repo.insert_attachments.assert_called_once_with([])
        assert structures == []
        assert tables == []
        assert attachments == []
        assert ss == []
        assert ts == []
        assert ats == []

    async def test_single_contrib_no_components_produces_empty_slices(self):
        svc, _, struct_repo, table_repo, attach_repo = _make_service()
        struct_repo.insert_structures.return_value = []
        table_repo.insert_tables.return_value = []
        attach_repo.insert_attachments.return_value = []

        contrib = _contrib_in()
        _, _, _, ss, ts, ats = await svc._insert_components([contrib])

        assert ss == [slice(0, 0)]
        assert ts == [slice(0, 0)]
        assert ats == [slice(0, 0)]

    async def test_slices_are_contiguous_and_non_overlapping(self):
        svc, _, struct_repo, table_repo, attach_repo = _make_service()

        struct_repo.insert_structures.return_value = [_fake_structure()] * 3
        table_repo.insert_tables.return_value = []
        attach_repo.insert_attachments.return_value = []

        contrib_a = _contrib_in(identifier="a", structures=[_structure_in()])
        contrib_b = _contrib_in(identifier="b", structures=[_structure_in(), _structure_in()])
        contrib_c = _contrib_in(identifier="c")

        _, _, _, ss, _, _ = await svc._insert_components([contrib_a, contrib_b, contrib_c])

        assert ss[0] == slice(0, 1)   # contrib_a: 1 structure
        assert ss[1] == slice(1, 3)   # contrib_b: 2 structures
        assert ss[2] == slice(3, 3)   # contrib_c: 0 structures

    async def test_all_component_types_collected_and_dispatched(self):
        svc, _, struct_repo, table_repo, attach_repo = _make_service()

        struct_repo.insert_structures.return_value = [_fake_structure()]
        table_repo.insert_tables.return_value = [_fake_table()]
        attach_repo.insert_attachments.return_value = [_fake_attachment()]

        contrib = _contrib_in(
            structures=[_structure_in()],
            tables=[_table_in()],
            attachments=[_attachment_in()],
        )

        await svc._insert_components([contrib])

        struct_repo.insert_structures.assert_called_once()
        table_repo.insert_tables.assert_called_once()
        attach_repo.insert_attachments.assert_called_once()
        # Verify correct counts were forwarded
        assert len(struct_repo.insert_structures.call_args[0][0]) == 1
        assert len(table_repo.insert_tables.call_args[0][0]) == 1
        assert len(attach_repo.insert_attachments.call_args[0][0]) == 1

    async def test_multiple_contribs_components_concatenated_before_insert(self):
        svc, _, struct_repo, table_repo, attach_repo = _make_service()

        struct_repo.insert_structures.return_value = [_fake_structure()] * 3
        table_repo.insert_tables.return_value = []
        attach_repo.insert_attachments.return_value = []

        c1 = _contrib_in(identifier="c1", structures=[_structure_in()])
        c2 = _contrib_in(identifier="c2", structures=[_structure_in(), _structure_in()])

        await svc._insert_components([c1, c2])

        struct_repo.insert_structures.assert_called_once()
        assert len(struct_repo.insert_structures.call_args[0][0]) == 3


# ---------------------------------------------------------------------------
# insert_contributions
# ---------------------------------------------------------------------------


class TestInsertContributions:
    async def test_delegates_to_insert_many(self):
        svc, contrib_repo, struct_repo, table_repo, attach_repo = _make_service()

        struct_repo.insert_structures.return_value = []
        table_repo.insert_tables.return_value = []
        attach_repo.insert_attachments.return_value = []
        contrib_repo.insert_many_contributions.return_value = MagicMock()

        contribs = [_contrib_in(identifier=f"mp-{i}") for i in range(3)]
        await svc.insert_contributions(contribs)

        contrib_repo.insert_many_contributions.assert_called_once()
        inserted_docs = contrib_repo.insert_many_contributions.call_args[0][0]
        assert len(inserted_docs) == 3

    async def test_is_public_forced_false_on_all_docs(self):
        svc, contrib_repo, struct_repo, table_repo, attach_repo = _make_service()

        struct_repo.insert_structures.return_value = []
        table_repo.insert_tables.return_value = []
        attach_repo.insert_attachments.return_value = []
        contrib_repo.insert_many_contributions.return_value = MagicMock()

        contribs = [_contrib_in(identifier="mp-1")]
        await svc.insert_contributions(contribs)

        docs = contrib_repo.insert_many_contributions.call_args[0][0]
        assert all(d.is_public is False for d in docs)

    async def test_structure_links_wired_correctly(self):
        svc, contrib_repo, struct_repo, table_repo, attach_repo = _make_service()

        fake_struct = _fake_structure()
        struct_repo.insert_structures.return_value = [fake_struct]
        table_repo.insert_tables.return_value = []
        attach_repo.insert_attachments.return_value = []
        contrib_repo.insert_many_contributions.return_value = MagicMock()

        contrib = _contrib_in(structures=[_structure_in()])
        await svc.insert_contributions([contrib])

        doc = contrib_repo.insert_many_contributions.call_args[0][0][0]
        assert doc.structures == [fake_struct]

    async def test_table_links_wired_correctly(self):
        svc, contrib_repo, struct_repo, table_repo, attach_repo = _make_service()

        fake_table = _fake_table()
        struct_repo.insert_structures.return_value = []
        table_repo.insert_tables.return_value = [fake_table]
        attach_repo.insert_attachments.return_value = []
        contrib_repo.insert_many_contributions.return_value = MagicMock()

        contrib = _contrib_in(tables=[_table_in()])
        await svc.insert_contributions([contrib])

        doc = contrib_repo.insert_many_contributions.call_args[0][0][0]
        assert doc.tables == [fake_table]

    async def test_attachment_links_wired_correctly(self):
        svc, contrib_repo, struct_repo, table_repo, attach_repo = _make_service()

        fake_attach = _fake_attachment()
        struct_repo.insert_structures.return_value = []
        table_repo.insert_tables.return_value = []
        attach_repo.insert_attachments.return_value = [fake_attach]
        contrib_repo.insert_many_contributions.return_value = MagicMock()

        contrib = _contrib_in(attachments=[_attachment_in()])
        await svc.insert_contributions([contrib])

        doc = contrib_repo.insert_many_contributions.call_args[0][0][0]
        assert doc.attachments == [fake_attach]

    async def test_no_components_sets_links_to_none(self):
        svc, contrib_repo, struct_repo, table_repo, attach_repo = _make_service()

        struct_repo.insert_structures.return_value = []
        table_repo.insert_tables.return_value = []
        attach_repo.insert_attachments.return_value = []
        contrib_repo.insert_many_contributions.return_value = MagicMock()

        await svc.insert_contributions([_contrib_in()])

        doc = contrib_repo.insert_many_contributions.call_args[0][0][0]
        assert doc.structures is None
        assert doc.tables is None
        assert doc.attachments is None

    async def test_each_contrib_gets_only_its_own_components(self):
        """Components belonging to contrib A must not bleed into contrib B."""
        svc, contrib_repo, struct_repo, table_repo, attach_repo = _make_service()

        s_a, s_b1, s_b2 = _fake_structure(), _fake_structure(), _fake_structure()
        struct_repo.insert_structures.return_value = [s_a, s_b1, s_b2]
        table_repo.insert_tables.return_value = []
        attach_repo.insert_attachments.return_value = []
        contrib_repo.insert_many_contributions.return_value = MagicMock()

        c_a = _contrib_in(identifier="a", structures=[_structure_in()])
        c_b = _contrib_in(identifier="b", structures=[_structure_in(), _structure_in()])

        await svc.insert_contributions([c_a, c_b])

        docs = contrib_repo.insert_many_contributions.call_args[0][0]
        assert docs[0].structures == [s_a]
        assert docs[1].structures == [s_b1, s_b2]

    async def test_empty_batch_still_calls_insert_many(self):
        svc, contrib_repo, struct_repo, table_repo, attach_repo = _make_service()

        struct_repo.insert_structures.return_value = []
        table_repo.insert_tables.return_value = []
        attach_repo.insert_attachments.return_value = []
        contrib_repo.insert_many_contributions.return_value = MagicMock()

        await svc.insert_contributions([])

        contrib_repo.insert_many_contributions.assert_called_once_with([])


# ---------------------------------------------------------------------------
# upsert_contributions — guard clause
# ---------------------------------------------------------------------------


class TestUpsertContributionsGuard:
    async def test_raises_validation_error_when_any_contrib_has_structures(self):
        svc, *_ = _make_service()
        contrib = _contrib_in(structures=[_structure_in()])
        with pytest.raises(ValidationError):
            await svc.upsert_contributions([contrib])

    async def test_raises_validation_error_when_any_contrib_has_tables(self):
        svc, *_ = _make_service()
        contrib = _contrib_in(tables=[_table_in()])
        with pytest.raises(ValidationError):
            await svc.upsert_contributions([contrib])

    async def test_raises_validation_error_when_any_contrib_has_attachments(self):
        svc, *_ = _make_service()
        contrib = _contrib_in(attachments=[_attachment_in()])
        with pytest.raises(ValidationError):
            await svc.upsert_contributions([contrib])

    async def test_error_reports_indices_of_offending_contribs(self):
        svc, *_ = _make_service()
        clean = _contrib_in(identifier="clean")
        dirty = _contrib_in(identifier="dirty", structures=[_structure_in()])
        with pytest.raises(ValidationError) as exc_info:
            await svc.upsert_contributions([clean, dirty])
        assert exc_info.value.context.get("contribution_indices") == [1]

    async def test_multiple_offenders_all_indices_reported(self):
        svc, *_ = _make_service()
        contribs = [
            _contrib_in(identifier="c0", structures=[_structure_in()]),
            _contrib_in(identifier="c1"),
            _contrib_in(identifier="c2", tables=[_table_in()]),
        ]
        with pytest.raises(ValidationError) as exc_info:
            await svc.upsert_contributions(contribs)
        assert exc_info.value.context.get("contribution_indices") == [0, 2]

    async def test_raises_before_any_db_write(self):
        svc, contrib_repo, *_ = _make_service()
        dirty = _contrib_in(structures=[_structure_in()])
        with pytest.raises(ValidationError):
            await svc.upsert_contributions([dirty])
        contrib_repo.find_one_contribution.assert_not_called()
        contrib_repo.insert_contribution.assert_not_called()
        contrib_repo.update_contribution.assert_not_called()


# ---------------------------------------------------------------------------
# upsert_contributions — insert path (no existing doc)
# ---------------------------------------------------------------------------


class TestUpsertContributionsInsertPath:
    async def test_insert_called_when_no_existing_doc(self):
        svc, contrib_repo, *_ = _make_service()
        contrib_repo.find_one_contribution.return_value = None
        inserted = MagicMock(spec=Contribution)
        contrib_repo.insert_contribution.return_value = inserted

        result = await svc.upsert_contributions([_contrib_in()])

        contrib_repo.insert_contribution.assert_called_once()
        assert result[0] is inserted

    async def test_new_doc_is_public_false(self):
        svc, contrib_repo, *_ = _make_service()
        contrib_repo.find_one_contribution.return_value = None

        captured = []

        async def _capture(doc):
            captured.append(doc)
            return doc

        contrib_repo.insert_contribution.side_effect = _capture

        await svc.upsert_contributions([_contrib_in()])

        assert len(captured) == 1
        assert captured[0].is_public is False

    async def test_find_uses_project_and_identifier(self):
        svc, contrib_repo, *_ = _make_service()
        contrib_repo.find_one_contribution.return_value = None
        contrib_repo.insert_contribution.return_value = MagicMock(spec=Contribution)

        contrib = _contrib_in(project="my-proj", identifier="mp-99")
        await svc.upsert_contributions([contrib])

        contrib_repo.find_one_contribution.assert_called_once_with("my-proj", "mp-99")

    async def test_update_not_called_on_insert_path(self):
        svc, contrib_repo, *_ = _make_service()
        contrib_repo.find_one_contribution.return_value = None
        contrib_repo.insert_contribution.return_value = MagicMock(spec=Contribution)

        await svc.upsert_contributions([_contrib_in()])

        contrib_repo.update_contribution.assert_not_called()


# ---------------------------------------------------------------------------
# upsert_contributions — update path (existing doc found)
# ---------------------------------------------------------------------------


class TestUpsertContributionsUpdatePath:
    async def test_update_called_when_existing_doc_found(self):
        svc, contrib_repo, *_ = _make_service()
        existing = MagicMock(spec=Contribution)
        contrib_repo.find_one_contribution.return_value = existing
        contrib_repo.update_contribution.return_value = None

        await svc.upsert_contributions([_contrib_in()])

        contrib_repo.update_contribution.assert_called_once()

    async def test_returns_existing_doc_on_update(self):
        svc, contrib_repo, *_ = _make_service()
        existing = MagicMock(spec=Contribution)
        contrib_repo.find_one_contribution.return_value = existing
        contrib_repo.update_contribution.return_value = None

        result = await svc.upsert_contributions([_contrib_in()])

        assert result[0] is existing

    async def test_insert_not_called_on_update_path(self):
        svc, contrib_repo, *_ = _make_service()
        existing = MagicMock(spec=Contribution)
        contrib_repo.find_one_contribution.return_value = existing
        contrib_repo.update_contribution.return_value = None

        await svc.upsert_contributions([_contrib_in()])

        contrib_repo.insert_contribution.assert_not_called()

    async def test_update_data_excludes_id(self):
        svc, contrib_repo, *_ = _make_service()
        existing = MagicMock(spec=Contribution)
        contrib_repo.find_one_contribution.return_value = existing
        contrib_repo.update_contribution.return_value = None

        await svc.upsert_contributions([_contrib_in(formula="SiO2")])

        update_data = contrib_repo.update_contribution.call_args[0][1]
        assert "id" not in update_data

    async def test_update_data_excludes_none_fields(self):
        svc, contrib_repo, *_ = _make_service()
        existing = MagicMock(spec=Contribution)
        contrib_repo.find_one_contribution.return_value = existing
        contrib_repo.update_contribution.return_value = None

        await svc.upsert_contributions([_contrib_in(formula="SiO2")])

        update_data = contrib_repo.update_contribution.call_args[0][1]
        assert all(v is not None for v in update_data.values())


# ---------------------------------------------------------------------------
# upsert_contributions — concurrent batch behavior
# ---------------------------------------------------------------------------


class TestUpsertContributionsBatch:
    async def test_all_contribs_processed(self):
        svc, contrib_repo, *_ = _make_service()
        contrib_repo.find_one_contribution.return_value = None
        contrib_repo.insert_contribution.return_value = MagicMock(spec=Contribution)

        contribs = [_contrib_in(identifier=f"mp-{i}") for i in range(5)]
        results = await svc.upsert_contributions(contribs)

        assert len(results) == 5
        assert contrib_repo.insert_contribution.call_count == 5

    async def test_mixed_insert_and_update_batch(self):
        svc, contrib_repo, *_ = _make_service()
        existing = MagicMock(spec=Contribution)

        async def _find(project, identifier):
            return existing if identifier == "mp-0" else None

        contrib_repo.find_one_contribution.side_effect = _find
        contrib_repo.update_contribution.return_value = None
        contrib_repo.insert_contribution.return_value = MagicMock(spec=Contribution)

        contribs = [_contrib_in(identifier=f"mp-{i}") for i in range(3)]
        await svc.upsert_contributions(contribs)

        assert contrib_repo.update_contribution.call_count == 1
        assert contrib_repo.insert_contribution.call_count == 2

    async def test_empty_batch_returns_empty_list(self):
        svc, *_ = _make_service()
        results = await svc.upsert_contributions([])
        assert results == []


