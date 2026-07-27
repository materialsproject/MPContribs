import asyncio
from unittest.mock import AsyncMock, MagicMock

import polars as pl
import pytest
from beanie import PydanticObjectId
from pymatgen.core import Element
from pymongo.errors import BulkWriteError

from mpcontribs_api.authz import ADMIN_GROUP, User
from mpcontribs_api.config import MongoSettings
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
from mpcontribs_api.exceptions import ConflictError, ValidationError

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


def _contrib_in(
    project="proj",
    material_id="mp-1",
    chemical_system_id="Fe-O",
    formula="Fe2O3",
    identifier=None,
    data=None,
    **kwargs,
) -> ContributionIn:
    # Many tests pass ``identifier=`` to mint distinct contributions; map it onto material_id so the
    # identity tuple (project, material_id, chemical_system_id, formula, unique_value) differs.
    if identifier is not None:
        material_id = identifier
    return ContributionIn(
        _id=_oid(),
        project=project,
        material_id=material_id,
        chemical_system_id=chemical_system_id,
        formula=formula,
        data={} if data is None else data,
        **kwargs,
    )


def _make_mongo_settings(
    *,
    max_components_per_contribution: int = 500,
    max_concurrent_transactions: int = 8,
    component_insert_chunk_size: int = 100,
) -> MongoSettings:
    return MongoSettings.model_validate({
        "uri": "mongodb://test",
        "db_name": "test",
        "max_pool_size": 100,
        "max_components_per_contribution": max_components_per_contribution,
        "max_concurrent_transactions": max_concurrent_transactions,
        "component_insert_chunk_size": component_insert_chunk_size,
    })


def _make_fake_client() -> tuple[AsyncMock, MagicMock]:
    """Return a fake AsyncMongoClient whose start_session() yields a session that drives
    with_transaction(callback) by simply awaiting callback(session).

    Returns:
        (client, session): the session is exposed so tests can assert on it.
    """
    session = MagicMock(name="session")

    async def _with_transaction(callback):
        return await callback(session)

    session.with_transaction = AsyncMock(side_effect=_with_transaction)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    client = MagicMock(name="client")
    client.start_session = MagicMock(return_value=session)
    return client, session


def _admin_user() -> User:
    """An admin user — bypasses project write authorization, so tests not exercising authz
    keep their previous behavior."""
    return User(username="admin", groups=frozenset({ADMIN_GROUP}))


def _make_service(
    contributions=None,
    structures=None,
    tables=None,
    attachments=None,
    client=None,
    settings: MongoSettings | None = None,
    write_slots: asyncio.Semaphore | None = None,
    user: User | None = None,
    projects=None,
    unique_column: str | None = None,
) -> tuple[ContributionService, AsyncMock, AsyncMock, AsyncMock, AsyncMock, MagicMock]:
    contrib_repo = contributions or AsyncMock()
    struct_repo = structures or AsyncMock()
    table_repo = tables or AsyncMock()
    attach_repo = attachments or AsyncMock()
    # Default identity resolution: every referenced project reports its ``unique_column`` (None by
    # default -> identity is the fixed-field triple), and no identity exists yet, so the common path
    # resolves with no conflict. Tests exercising duplicates override ``existing_identities``.
    projects_repo = projects or AsyncMock()
    if projects is None:
        projects_repo.unique_columns_by_id.side_effect = lambda ids: {pid: unique_column for pid in ids}
    contrib_repo.existing_identities.return_value = set()
    if client is None:
        client, _ = _make_fake_client()
    svc = ContributionService(
        client=client,
        user=user or _admin_user(),
        projects=projects_repo,
        contributions=contrib_repo,
        structures=struct_repo,
        tables=table_repo,
        attachments=attach_repo,
        settings=settings or _make_mongo_settings(),
    )
    return svc, contrib_repo, struct_repo, table_repo, attach_repo, client


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
# insert_contributions — pre-checks (cheap, no DB)
# ---------------------------------------------------------------------------


class TestInsertContributionsPreChecks:
    async def test_empty_batch_returns_empty_summary_no_db(self):
        svc, contrib_repo, struct_repo, table_repo, attach_repo, client = _make_service()

        summary = await svc.insert_contributions([])

        assert summary.total == 0
        assert summary.succeeded == []
        assert summary.failed == []
        contrib_repo.insert_many_contributions.assert_not_called()
        contrib_repo.insert_contribution.assert_not_called()
        client.start_session.assert_not_called()

    async def test_duplicate_identity_in_one_batch_conflicts_later_item(self):
        """A repeated identity within one batch does not fail the whole request: the first occurrence
        is inserted; later intra-batch duplicates are per-item conflict failures."""
        svc, contrib_repo, _, _, _, client = _make_service()
        contrib_repo.insert_many_contributions.return_value = None
        contribs = [
            _contrib_in(project="p", identifier="dup"),
            _contrib_in(project="p", identifier="dup"),
        ]
        summary = await svc.insert_contributions(contribs)

        assert summary.total == 2
        assert len(summary.succeeded) == 1
        assert [f.index for f in summary.failed] == [1]
        assert summary.failed[0].error_code == "conflict"
        # Index 0 still reached Mongo (one doc inserted)
        assert len(contrib_repo.insert_many_contributions.call_args[0][0]) == 1

    async def test_oversize_contribution_goes_to_failures_without_db(self):
        settings = _make_mongo_settings(max_components_per_contribution=1)
        svc, contrib_repo, struct_repo, _, _, client = _make_service(settings=settings)
        contrib_repo.insert_many_contributions.return_value = None

        good = _contrib_in(identifier="ok")
        oversize = _contrib_in(identifier="big", structures=[_structure_in(), _structure_in()])

        summary = await svc.insert_contributions([good, oversize])

        assert summary.total == 2
        assert len(summary.failed) == 1
        assert summary.failed[0].index == 1
        assert summary.failed[0].error_code == "validation_error"
        # Oversize never reached the component repo
        struct_repo.insert_components.assert_not_called()
        # And the in-pool contribution did go through the no-component fast path
        contrib_repo.insert_many_contributions.assert_called_once()


# ---------------------------------------------------------------------------
# insert_contributions — no-component fast path
# ---------------------------------------------------------------------------


class TestInsertContributionsNoComponentPath:
    async def test_all_no_components_uses_single_insert_many(self):
        svc, contrib_repo, _, _, _, client = _make_service()
        contrib_repo.insert_many_contributions.return_value = None

        contribs = [_contrib_in(identifier=f"mp-{i}") for i in range(3)]
        summary = await svc.insert_contributions(contribs)

        contrib_repo.insert_many_contributions.assert_called_once()
        # Zero transactions opened
        client.start_session.assert_not_called()
        contrib_repo.insert_contribution.assert_not_called()
        assert summary.total == 3
        assert len(summary.succeeded) == 3
        assert summary.failed == []

    async def test_is_public_forced_false_on_inserted_docs(self):
        svc, contrib_repo, _, _, _, _ = _make_service()
        contrib_repo.insert_many_contributions.return_value = None

        await svc.insert_contributions([_contrib_in()])

        docs = contrib_repo.insert_many_contributions.call_args[0][0]
        assert all(d.is_public is False for d in docs)

    async def test_bulk_write_error_partitions_succeeded_and_failed(self):
        svc, contrib_repo, _, _, _, _ = _make_service()
        # writeErrors index refers to position in the docs list (post-partition); both 2 and 5
        # exercise the mapping back to original input indices.
        bulk_err = BulkWriteError({
            "writeErrors": [
                {"index": 2, "code": 11000, "errmsg": "duplicate key"},
                {"index": 5, "code": 11000, "errmsg": "duplicate key"},
            ]
        })
        contrib_repo.insert_many_contributions.side_effect = bulk_err

        contribs = [_contrib_in(identifier=f"mp-{i}") for i in range(6)]
        summary = await svc.insert_contributions(contribs)

        assert summary.total == 6
        assert sorted(f.index for f in summary.failed) == [2, 5]
        assert all(f.error_code == "conflict" for f in summary.failed)
        # The 4 unaffected contributions succeed
        assert len(summary.succeeded) == 4


# ---------------------------------------------------------------------------
# insert_contributions — per-contribution transaction path
# ---------------------------------------------------------------------------


class TestInsertContributionsTransactionPath:
    async def test_with_components_opens_session_per_contribution(self):
        svc, contrib_repo, struct_repo, table_repo, attach_repo, client = _make_service()

        struct_repo.insert_components.return_value = [_fake_structure()]
        table_repo.insert_components.return_value = []
        attach_repo.insert_components.return_value = []

        async def _insert(doc, session=None):
            return doc

        contrib_repo.insert_contribution.side_effect = _insert

        contribs = [_contrib_in(identifier=f"c{i}", structures=[_structure_in()]) for i in range(3)]
        summary = await svc.insert_contributions(contribs)

        assert client.start_session.call_count == 3
        assert summary.total == 3
        assert len(summary.succeeded) == 3
        assert summary.failed == []

    async def test_session_threaded_to_all_repo_calls(self):
        client, session = _make_fake_client()
        svc, contrib_repo, struct_repo, table_repo, _, _ = _make_service(client=client)

        struct_repo.insert_components.return_value = [_fake_structure()]
        table_repo.insert_components.return_value = [_fake_table()]

        async def _insert(doc, session=None):
            return doc

        contrib_repo.insert_contribution.side_effect = _insert

        contrib = _contrib_in(
            structures=[_structure_in()],
            tables=[_table_in()],
            attachments=[_attachment_in()],
        )
        await svc.insert_contributions([contrib])
        assert struct_repo.insert_components.call_args.kwargs["session"] is session
        assert table_repo.insert_components.call_args.kwargs["session"] is session
        assert contrib_repo.insert_contribution.call_args.kwargs["session"] is session

    async def test_failure_on_second_of_three_yields_summary(self):
        svc, contrib_repo, struct_repo, table_repo, attach_repo, _ = _make_service()

        struct_repo.insert_components.return_value = [_fake_structure()]
        table_repo.insert_components.return_value = []
        attach_repo.insert_components.return_value = []

        async def _insert(doc, session=None):
            # Fail the second contribution by inspecting the doc's material_id
            if doc.material_id == "fail":
                raise ConflictError("conflict on insert")
            return doc

        contrib_repo.insert_contribution.side_effect = _insert

        contribs = [
            _contrib_in(identifier="ok-1", structures=[_structure_in()]),
            _contrib_in(identifier="fail", structures=[_structure_in()]),
            _contrib_in(identifier="ok-2", structures=[_structure_in()]),
        ]
        summary = await svc.insert_contributions(contribs)

        assert summary.total == 3
        assert len(summary.succeeded) == 2
        assert len(summary.failed) == 1
        assert summary.failed[0].index == 1
        assert summary.failed[0].error_code == "conflict"

    async def test_component_links_wired_per_contribution(self):
        svc, contrib_repo, struct_repo, table_repo, attach_repo, _ = _make_service()

        struct_a, struct_b = _fake_structure(), _fake_structure()
        struct_calls = iter([[struct_a], [struct_b]])
        struct_repo.insert_components.side_effect = lambda *_args, **_kwargs: next(struct_calls)
        table_repo.insert_components.return_value = []
        attach_repo.insert_components.return_value = []

        captured: list[Contribution] = []

        async def _insert(doc, session=None):
            captured.append(doc)
            return doc

        contrib_repo.insert_contribution.side_effect = _insert

        contribs = [
            _contrib_in(identifier="a", structures=[_structure_in()]),
            _contrib_in(identifier="b", structures=[_structure_in()]),
        ]
        await svc.insert_contributions(contribs)

        captured_by_id = {c.material_id: c for c in captured}
        assert captured_by_id["a"].structures == [struct_a]
        assert captured_by_id["b"].structures == [struct_b]


# ---------------------------------------------------------------------------
# insert_contributions — mixed batch (partitioned across paths)
# ---------------------------------------------------------------------------


class TestInsertContributionsMixedBatch:
    async def test_mixed_batch_routes_correctly(self):
        svc, contrib_repo, struct_repo, table_repo, attach_repo, client = _make_service()

        struct_repo.insert_components.return_value = [_fake_structure()]
        table_repo.insert_components.return_value = []
        attach_repo.insert_components.return_value = []
        contrib_repo.insert_many_contributions.return_value = None

        async def _insert(doc, session=None):
            return doc

        contrib_repo.insert_contribution.side_effect = _insert

        contribs = [
            _contrib_in(identifier="bare-1"),
            _contrib_in(identifier="with-1", structures=[_structure_in()]),
            _contrib_in(identifier="bare-2"),
            _contrib_in(identifier="with-2", structures=[_structure_in()]),
        ]
        summary = await svc.insert_contributions(contribs)

        # No-component path: single batched call
        contrib_repo.insert_many_contributions.assert_called_once()
        assert len(contrib_repo.insert_many_contributions.call_args[0][0]) == 2
        # With-component path: one session per item
        assert client.start_session.call_count == 2
        assert contrib_repo.insert_contribution.call_count == 2
        assert summary.total == 4
        assert len(summary.succeeded) == 4
        assert summary.failed == []


# ---------------------------------------------------------------------------
# Versioning — uniqueness rules + version assignment (insert & upsert)
# ---------------------------------------------------------------------------


def _projects_mock(unique_map: dict[str, str | None]) -> AsyncMock:
    """A projects repo whose unique_columns_by_id returns only the known projects.

    ``unique_map`` maps each known project id to its ``unique_column`` (or None). Projects absent from
    the map are treated as not found/accessible.
    """
    repo = AsyncMock()
    repo.unique_columns_by_id.side_effect = lambda ids: {pid: unique_map[pid] for pid in ids if pid in unique_map}
    return repo


class TestContributionIdentity:
    async def test_insert_existing_identity_conflicts(self):
        svc, contrib_repo, *_ = _make_service()
        contrib_repo.insert_many_contributions.return_value = None
        contrib_repo.existing_identities.return_value = {("proj", "mp-1", "Fe-O", "Fe2O3", None, "")}

        summary = await svc.insert_contributions([_contrib_in(identifier="mp-1")])

        assert summary.total == 1
        assert summary.succeeded == []
        assert [f.error_code for f in summary.failed] == ["conflict"]
        contrib_repo.insert_many_contributions.assert_not_called()

    async def test_insert_no_existing_identity_succeeds(self):
        svc, contrib_repo, *_ = _make_service()
        contrib_repo.insert_many_contributions.return_value = None

        summary = await svc.insert_contributions([_contrib_in(identifier="mp-1")])

        assert len(summary.succeeded) == 1
        docs = contrib_repo.insert_many_contributions.call_args[0][0]
        assert docs[0].unique_value is None

    async def test_insert_unique_column_promotes_value_to_unique_value(self):
        svc, contrib_repo, *_ = _make_service(unique_column="sample_id")
        contrib_repo.insert_many_contributions.return_value = None

        summary = await svc.insert_contributions([_contrib_in(data={"sample_id": "A"})])

        assert len(summary.succeeded) == 1
        docs = contrib_repo.insert_many_contributions.call_args[0][0]
        assert docs[0].unique_value == "A"

    async def test_insert_same_triple_distinct_unique_value_both_succeed(self):
        svc, contrib_repo, *_ = _make_service(unique_column="sample_id")
        contrib_repo.insert_many_contributions.return_value = None

        contribs = [_contrib_in(data={"sample_id": "A"}), _contrib_in(data={"sample_id": "B"})]
        summary = await svc.insert_contributions(contribs)

        assert len(summary.succeeded) == 2
        docs = contrib_repo.insert_many_contributions.call_args[0][0]
        assert sorted(d.unique_value for d in docs) == ["A", "B"]

    async def test_insert_missing_unique_column_value_is_validation_failure(self):
        svc, contrib_repo, *_ = _make_service(unique_column="sample_id")
        contrib_repo.insert_many_contributions.return_value = None

        summary = await svc.insert_contributions([_contrib_in(data={"other": 1})])

        assert summary.succeeded == []
        assert [f.error_code for f in summary.failed] == ["validation_error"]
        contrib_repo.insert_many_contributions.assert_not_called()

    async def test_insert_non_scalar_unique_column_value_is_validation_failure(self):
        svc, contrib_repo, *_ = _make_service(unique_column="sample_id")
        contrib_repo.insert_many_contributions.return_value = None

        summary = await svc.insert_contributions([_contrib_in(data={"sample_id": {"nested": 1}})])

        assert summary.succeeded == []
        assert [f.error_code for f in summary.failed] == ["validation_error"]

    async def test_insert_empty_unique_column_dup_triple_conflicts(self):
        """With no unique_column, two contributions sharing the fixed-field triple collide."""
        svc, contrib_repo, *_ = _make_service()  # unique_column=None
        contrib_repo.insert_many_contributions.return_value = None

        contribs = [_contrib_in(identifier="mp-1"), _contrib_in(identifier="mp-1")]
        summary = await svc.insert_contributions(contribs)

        assert len(summary.succeeded) == 1
        assert [f.error_code for f in summary.failed] == ["conflict"]

    async def test_insert_project_not_found_is_validation_failure(self):
        svc, contrib_repo, *_ = _make_service(projects=_projects_mock({}))  # no projects known

        summary = await svc.insert_contributions([_contrib_in(identifier="mp-1")])

        assert summary.succeeded == []
        assert [f.error_code for f in summary.failed] == ["validation_error"]
        contrib_repo.insert_many_contributions.assert_not_called()

    async def test_upsert_does_not_conflict_on_existing_identity(self):
        """Upsert targets an existing identity (update), so it must not pre-reject as a conflict."""
        svc, contrib_repo, *_ = _make_service()
        contrib_repo.upsert_contribution_by_identifiers.return_value = MagicMock(spec=Contribution)

        await svc.upsert_contributions([_contrib_in(identifier="mp-1")])

        # existing_identities is not consulted on the upsert path
        contrib_repo.existing_identities.assert_not_called()
        contrib_repo.upsert_contribution_by_identifiers.assert_called_once()

    async def test_upsert_passes_resolved_unique_value_in_identifiers(self):
        svc, contrib_repo, *_ = _make_service(unique_column="sample_id")
        contrib_repo.upsert_contribution_by_identifiers.return_value = MagicMock(spec=Contribution)

        await svc.upsert_contributions([_contrib_in(data={"sample_id": "A"})])

        identifiers = contrib_repo.upsert_contribution_by_identifiers.call_args.args[0]
        assert identifiers["unique_value"] == "A"

    async def test_upsert_missing_unique_column_value_is_validation_failure(self):
        svc, contrib_repo, *_ = _make_service(unique_column="sample_id")

        summary = await svc.upsert_contributions([_contrib_in(data={"other": 1})])

        assert summary.succeeded == []
        assert [f.error_code for f in summary.failed] == ["validation_error"]
        contrib_repo.upsert_contribution_by_identifiers.assert_not_called()


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
        contrib_repo.upsert_contribution_by_identifiers.assert_not_called()
        contrib_repo.find_one_contribution.assert_not_called()
        contrib_repo.insert_contribution.assert_not_called()
        contrib_repo.update_contribution.assert_not_called()


# ---------------------------------------------------------------------------
# upsert_contributions — atomic dispatch
# ---------------------------------------------------------------------------


class TestUpsertContributionsAtomic:
    async def test_calls_atomic_repo_method_once_per_item(self):
        svc, contrib_repo, *_ = _make_service()
        contrib_repo.upsert_contribution_by_identifiers.return_value = MagicMock(spec=Contribution)

        contribs = [_contrib_in(identifier=f"mp-{i}") for i in range(3)]
        summary = await svc.upsert_contributions(contribs)

        assert summary.total == 3
        assert len(summary.succeeded) == 3
        assert summary.failed == []
        assert contrib_repo.upsert_contribution_by_identifiers.call_count == 3
        # The legacy read-then-write path must not be used
        contrib_repo.find_one_contribution.assert_not_called()
        contrib_repo.update_contribution.assert_not_called()
        contrib_repo.insert_contribution.assert_not_called()

    async def test_passes_identifiers_dict_and_input_to_repo(self):
        svc, contrib_repo, *_ = _make_service()
        contrib_repo.upsert_contribution_by_identifiers.return_value = MagicMock(spec=Contribution)

        contrib = _contrib_in(project="my-proj", material_id="mp-99")
        await svc.upsert_contributions([contrib])

        call = contrib_repo.upsert_contribution_by_identifiers.call_args
        assert call.args[0] == {
            "project": "my-proj",
            "material_id": "mp-99",
            "chemical_system_id": "Fe-O",
            "formula": "Fe2O3",
            "unique_value": None,
            "condition_key": "",
        }
        assert call.args[1] is contrib

    async def test_returns_repo_results_in_input_order(self):
        svc, contrib_repo, *_ = _make_service()
        docs = [MagicMock(spec=Contribution, name=f"doc-{i}") for i in range(3)]
        returned = {}

        async def _upsert(identifiers, contrib):
            doc = docs[int(contrib.material_id.split("-")[1])]
            returned[contrib.material_id] = doc
            return doc

        contrib_repo.upsert_contribution_by_identifiers.side_effect = _upsert

        contribs = [_contrib_in(identifier=f"mp-{i}") for i in range(3)]
        summary = await svc.upsert_contributions(contribs)

        assert summary.succeeded == [returned["mp-0"], returned["mp-1"], returned["mp-2"]]

    async def test_empty_batch_returns_empty_summary(self):
        svc, contrib_repo, *_ = _make_service()
        summary = await svc.upsert_contributions([])
        assert summary.total == 0
        assert summary.succeeded == []
        assert summary.failed == []
        contrib_repo.upsert_contribution_by_identifiers.assert_not_called()

    async def test_same_key_concurrent_upserts_both_go_through_atomic_call(self):
        """Race-safety regression: two items with the same (project, identifier) in one batch
        must both reach the atomic repo method. The repo (via the unique index) is the
        tiebreaker — the service must not pre-deduplicate or otherwise swallow one.
        """
        svc, contrib_repo, *_ = _make_service()
        contrib_repo.upsert_contribution_by_identifiers.return_value = MagicMock(spec=Contribution)

        contribs = [
            _contrib_in(project="p", identifier="same"),
            _contrib_in(project="p", identifier="same"),
        ]
        summary = await svc.upsert_contributions(contribs)

        assert len(summary.succeeded) == 2
        assert contrib_repo.upsert_contribution_by_identifiers.call_count == 2

    async def test_one_failure_is_reported_not_raised(self):
        svc, contrib_repo, *_ = _make_service()

        async def _upsert(identifiers, contrib):
            if contrib.material_id == "mp-1":
                raise ConflictError("boom")
            return MagicMock(spec=Contribution)

        contrib_repo.upsert_contribution_by_identifiers.side_effect = _upsert

        contribs = [_contrib_in(identifier=f"mp-{i}") for i in range(3)]
        summary = await svc.upsert_contributions(contribs)

        assert summary.total == 3
        assert len(summary.succeeded) == 2
        assert [f.index for f in summary.failed] == [1]
        assert summary.failed[0].error_code == "conflict"


# ---------------------------------------------------------------------------
# Project-scoped write authorization (insert + upsert)
# ---------------------------------------------------------------------------


def _member_user(*projects: str) -> User:
    """Non-admin user whose writable projects are exactly ``projects``."""
    return User(username="alice", groups=frozenset(projects))


class TestWriteAuthorization:
    async def test_insert_rejects_unauthorized_project_per_item(self):
        svc, contrib_repo, struct_repo, _, _, client = _make_service(user=_member_user("allowed"))
        contrib_repo.insert_many_contributions.return_value = None

        contribs = [
            _contrib_in(project="allowed", identifier="ok"),
            _contrib_in(project="forbidden", identifier="nope"),
        ]
        summary = await svc.insert_contributions(contribs)

        assert summary.total == 2
        assert len(summary.succeeded) == 1
        assert [f.index for f in summary.failed] == [1]
        assert summary.failed[0].error_code == "permission_denied"
        assert "forbidden" in summary.failed[0].message
        # Only the authorized item reached Mongo
        contrib_repo.insert_many_contributions.assert_called_once()

    async def test_insert_admin_bypasses_authorization(self):
        svc, contrib_repo, *_ = _make_service()  # default user is admin
        contrib_repo.insert_many_contributions.return_value = None

        contribs = [_contrib_in(project="anything", identifier=f"mp-{i}") for i in range(2)]
        summary = await svc.insert_contributions(contribs)

        assert summary.total == 2
        assert len(summary.succeeded) == 2
        assert summary.failed == []

    async def test_insert_unauthorized_and_oversize_yield_single_failure(self):
        """An item that is both unauthorized and oversize must produce exactly one BulkFailure
        (authorization runs first), preserving total == len(contributions)."""
        settings = _make_mongo_settings(max_components_per_contribution=1)
        svc, contrib_repo, struct_repo, _, _, _ = _make_service(user=_member_user("allowed"), settings=settings)

        bad = _contrib_in(project="forbidden", identifier="big", structures=[_structure_in(), _structure_in()])
        summary = await svc.insert_contributions([bad])

        assert summary.total == 1
        assert len(summary.failed) == 1
        assert summary.failed[0].index == 0
        assert summary.failed[0].error_code == "permission_denied"
        struct_repo.insert_components.assert_not_called()

    async def test_upsert_rejects_unauthorized_project_per_item(self):
        svc, contrib_repo, *_ = _make_service(user=_member_user("allowed"))
        contrib_repo.upsert_contribution_by_identifiers.return_value = MagicMock(spec=Contribution)

        contribs = [
            _contrib_in(project="allowed", identifier="ok"),
            _contrib_in(project="forbidden", identifier="nope"),
        ]
        summary = await svc.upsert_contributions(contribs)

        assert summary.total == 2
        assert len(summary.succeeded) == 1
        assert [f.index for f in summary.failed] == [1]
        assert summary.failed[0].error_code == "permission_denied"
        assert "forbidden" in summary.failed[0].message
        # Only the authorized item reached the atomic repo method
        contrib_repo.upsert_contribution_by_identifiers.assert_called_once()

    async def test_upsert_anonymous_authorized_for_nothing(self):
        svc, contrib_repo, *_ = _make_service(user=User())  # anonymous: no username, no groups

        summary = await svc.upsert_contributions([_contrib_in(project="any", identifier="x")])

        assert summary.total == 1
        assert summary.succeeded == []
        assert [f.error_code for f in summary.failed] == ["permission_denied"]
        contrib_repo.upsert_contribution_by_identifiers.assert_not_called()


# ---------------------------------------------------------------------------
# Process-wide write_slots semaphore is honored
# ---------------------------------------------------------------------------


# class TestProcessWideWriteSlots:
#     async def test_upsert_acquires_global_write_slot(self):
#         write_slots = asyncio.Semaphore(1)
#         svc, contrib_repo, *_ = _make_service(write_slots=write_slots)

#         in_flight = 0
#         peak = 0

#         async def _upsert(identifiers, contrib):
#             nonlocal in_flight, peak
#             in_flight += 1
#             peak = max(peak, in_flight)
#             await asyncio.sleep(0)  # let other coroutines try to enter
#             in_flight -= 1
#             return MagicMock(spec=Contribution)

#         contrib_repo.upsert_contribution_by_identifiers.side_effect = _upsert

#         contribs = [_contrib_in(identifier=f"mp-{i}") for i in range(5)]
#         await svc.upsert_contributions(contribs)

#         assert peak == 1  # global semaphore of 1 must serialize all 5

#     async def test_insert_with_components_acquires_global_write_slot(self):
#         write_slots = asyncio.Semaphore(1)
#         svc, contrib_repo, struct_repo, table_repo, attach_repo, _ = _make_service(write_slots=write_slots)

#         struct_repo.insert_components.return_value = [_fake_structure()]
#         table_repo.insert_components.return_value = []
#         attach_repo.insert_components.return_value = []

#         in_flight = 0
#         peak = 0

#         async def _insert(doc, session=None):
#             nonlocal in_flight, peak
#             in_flight += 1
#             peak = max(peak, in_flight)
#             await asyncio.sleep(0)
#             in_flight -= 1
#             return doc

#         contrib_repo.insert_contribution.side_effect = _insert

#         contribs = [_contrib_in(identifier=f"c{i}", structures=[_structure_in()]) for i in range(4)]
#         await svc.insert_contributions(contribs)

#         assert peak == 1


# ---------------------------------------------------------------------------
# delete_contributions — cascade delete (components-first), cursor loop
# ---------------------------------------------------------------------------

from types import SimpleNamespace  # noqa: E402

from mpcontribs_api.domains._shared.models import DeleteResponse  # noqa: E402
from mpcontribs_api.domains.contributions.models import ContributionFilter  # noqa: E402
from mpcontribs_api.pagination import Page  # noqa: E402


def _link(ref_id: PydanticObjectId) -> SimpleNamespace:
    """Minimal stand-in for a Beanie Link: only ``.ref.id`` is read by the service."""
    return SimpleNamespace(ref=SimpleNamespace(id=ref_id))


def _contrib_doc(structures=None, attachments=None, tables=None, id_=None) -> SimpleNamespace:
    """A contribution page item exposing the attributes delete_contributions reads."""
    return SimpleNamespace(
        id=id_ or _oid(),
        structures=[_link(s) for s in (structures or [])],
        attachments=[_link(a) for a in (attachments or [])],
        tables=[_link(t) for t in (tables or [])],
    )


def _page(items) -> Page:
    return Page(items=items, next_cursor=None)


def _delete_result(n: int) -> SimpleNamespace:
    """Stand-in for pymongo DeleteResult (only ``.deleted_count`` is read)."""
    return SimpleNamespace(deleted_count=n)


def _noop_filter() -> ContributionFilter:
    return ContributionFilter()


class TestDeleteContributionsEmpty:
    async def test_empty_match_returns_zero_summary(self):
        svc, contrib_repo, *_ = _make_service()
        contrib_repo.get_contributions.return_value = _page([])
        contrib_repo.delete_contributions.return_value = _delete_result(0)

        summary = await svc.delete_contributions(_noop_filter())

        assert summary.num_deleted == 0
        assert summary.num_children_deleted == 0

    async def test_empty_match_does_not_call_child_repos(self):
        svc, contrib_repo, struct_repo, table_repo, attach_repo, _ = _make_service()
        contrib_repo.get_contributions.return_value = _page([])
        contrib_repo.delete_contributions.return_value = _delete_result(0)

        await svc.delete_contributions(_noop_filter())

        struct_repo.delete_by_ids.assert_not_called()
        table_repo.delete_by_ids.assert_not_called()
        attach_repo.delete_by_ids.assert_not_called()

    async def test_empty_match_terminates_after_one_page(self):
        svc, contrib_repo, *_ = _make_service()
        contrib_repo.get_contributions.return_value = _page([])
        contrib_repo.delete_contributions.return_value = _delete_result(0)

        await svc.delete_contributions(_noop_filter())

        assert contrib_repo.get_contributions.await_count == 1


class TestDeleteContributionsSinglePage:
    async def test_deletes_contributions_then_terminates(self):
        svc, contrib_repo, *_ = _make_service()
        docs = [_contrib_doc() for _ in range(3)]
        # First call returns the page; second returns empty so the loop ends.
        contrib_repo.get_contributions.side_effect = [_page(docs), _page([])]
        contrib_repo.delete_contributions.side_effect = [_delete_result(3), _delete_result(0)]

        summary = await svc.delete_contributions(_noop_filter())

        assert summary.num_deleted == 3

    async def test_no_components_means_no_child_deletes(self):
        svc, contrib_repo, struct_repo, table_repo, attach_repo, _ = _make_service()
        contrib_repo.get_contributions.side_effect = [_page([_contrib_doc()]), _page([])]
        contrib_repo.delete_contributions.side_effect = [_delete_result(1), _delete_result(0)]

        summary = await svc.delete_contributions(_noop_filter())

        struct_repo.delete_by_ids.assert_not_called()
        table_repo.delete_by_ids.assert_not_called()
        attach_repo.delete_by_ids.assert_not_called()
        assert summary.num_children_deleted == 0

    async def test_components_deleted_before_contributions(self):
        # Records call order across repos to assert children go first.
        order: list[str] = []
        svc, contrib_repo, struct_repo, table_repo, attach_repo, _ = _make_service()

        doc = _contrib_doc(structures=[_oid()], tables=[_oid()], attachments=[_oid()])
        contrib_repo.get_contributions.side_effect = [_page([doc]), _page([])]

        def _make_child_recorder(name):
            async def _record(ids, *a, **k):
                order.append(name)
                return DeleteResponse(num_deleted=1)

            return _record

        struct_repo.delete_by_ids.side_effect = _make_child_recorder("structures")
        table_repo.delete_by_ids.side_effect = _make_child_recorder("tables")
        attach_repo.delete_by_ids.side_effect = _make_child_recorder("attachments")

        async def _record_contrib(_filter, *a, **k):
            order.append("contributions")
            return _delete_result(1)

        contrib_repo.delete_contributions.side_effect = _record_contrib

        await svc.delete_contributions(_noop_filter())

        # The loop makes a final pass on the empty page that still issues one
        # (no-op) contribution delete before breaking, so there are two
        # "contributions" entries. The invariant under test: all three child
        # deletes happen before the first contribution delete.
        first_contrib = order.index("contributions")
        assert set(order[:first_contrib]) == {"structures", "tables", "attachments"}

    async def test_child_ids_collected_from_links(self):
        svc, contrib_repo, struct_repo, *_ = _make_service()
        s1, s2 = _oid(), _oid()
        doc = _contrib_doc(structures=[s1, s2])
        contrib_repo.get_contributions.side_effect = [_page([doc]), _page([])]
        struct_repo.delete_by_ids.return_value = DeleteResponse(num_deleted=2)
        contrib_repo.delete_contributions.side_effect = [_delete_result(1), _delete_result(0)]

        await svc.delete_contributions(_noop_filter())

        called_ids = struct_repo.delete_by_ids.await_args.args[0]
        assert set(called_ids) == {s1, s2}

    async def test_child_counts_accumulated_across_types(self):
        svc, contrib_repo, struct_repo, table_repo, attach_repo, _ = _make_service()
        doc = _contrib_doc(structures=[_oid()], tables=[_oid(), _oid()], attachments=[_oid()])
        contrib_repo.get_contributions.side_effect = [_page([doc]), _page([])]
        struct_repo.delete_by_ids.return_value = DeleteResponse(num_deleted=1)
        table_repo.delete_by_ids.return_value = DeleteResponse(num_deleted=2)
        attach_repo.delete_by_ids.return_value = DeleteResponse(num_deleted=1)
        contrib_repo.delete_contributions.side_effect = [_delete_result(1), _delete_result(0)]

        summary = await svc.delete_contributions(_noop_filter())

        assert summary.num_children_deleted == 4

    async def test_contributions_deleted_by_id_in_of_page(self):
        svc, contrib_repo, *_ = _make_service()
        ids = [_oid(), _oid()]
        docs = [_contrib_doc(id_=i) for i in ids]
        contrib_repo.get_contributions.side_effect = [_page(docs), _page([])]
        contrib_repo.delete_contributions.side_effect = [_delete_result(2), _delete_result(0)]

        await svc.delete_contributions(_noop_filter())

        first_call_filter = contrib_repo.delete_contributions.await_args_list[0].args[0]
        assert set(first_call_filter.id__in) == set(ids)


class TestDeleteContributionsMultiPage:
    async def test_loops_until_page_empty(self):
        svc, contrib_repo, *_ = _make_service()
        contrib_repo.get_contributions.side_effect = [
            _page([_contrib_doc() for _ in range(2)]),
            _page([_contrib_doc()]),
            _page([]),
        ]
        contrib_repo.delete_contributions.side_effect = [
            _delete_result(2),
            _delete_result(1),
            _delete_result(0),
        ]

        summary = await svc.delete_contributions(_noop_filter())

        assert summary.num_deleted == 3
        assert contrib_repo.get_contributions.await_count == 3

    async def test_children_accumulate_across_pages(self):
        svc, contrib_repo, struct_repo, *_ = _make_service()
        contrib_repo.get_contributions.side_effect = [
            _page([_contrib_doc(structures=[_oid()])]),
            _page([_contrib_doc(structures=[_oid()])]),
            _page([]),
        ]
        struct_repo.delete_by_ids.return_value = DeleteResponse(num_deleted=1)
        contrib_repo.delete_contributions.side_effect = [
            _delete_result(1),
            _delete_result(1),
            _delete_result(0),
        ]

        summary = await svc.delete_contributions(_noop_filter())

        assert summary.num_children_deleted == 2
        assert struct_repo.delete_by_ids.await_count == 2


class TestDeleteContributionsNoneComponents:
    """ContributionOut leaves unset component fields as None (not []).

    The cascade loop must tolerate None rather than raising TypeError on iteration.
    """

    async def test_none_component_fields_do_not_raise(self):
        svc, contrib_repo, struct_repo, table_repo, attach_repo, _ = _make_service()
        doc = SimpleNamespace(id=_oid(), structures=None, tables=None, attachments=None)
        contrib_repo.get_contributions.side_effect = [_page([doc]), _page([])]
        contrib_repo.delete_contributions.side_effect = [_delete_result(1), _delete_result(0)]

        summary = await svc.delete_contributions(_noop_filter())

        assert summary.num_deleted == 1
        assert summary.num_children_deleted == 0
        struct_repo.delete_by_ids.assert_not_called()
        table_repo.delete_by_ids.assert_not_called()
        attach_repo.delete_by_ids.assert_not_called()
