import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import polars as pl
import pytest
from beanie import PydanticObjectId
from pymatgen.core import Element
from pymongo.errors import BulkWriteError

from mpcontribs_api.authz import ADMIN_GROUP, User
from mpcontribs_api.config import MongoSettings, get_settings
from mpcontribs_api.domains.attachments.models import Attachment, AttachmentIn
from mpcontribs_api.domains.contributions.models import (
    Contribution,
    ContributionFilter,
    ContributionIdentity,
    ContributionIn,
    ContributionPatch,
)
from mpcontribs_api.domains.contributions import service as service_module
from mpcontribs_api.domains.contributions.service import ContributionService
from mpcontribs_api.domains.contributions.stats import ProjectAggregate
from mpcontribs_api.domains.structures.models import (
    Lattice,
    Site,
    SiteProperties,
    Species,
    Structure,
    StructureIn,
)
from mpcontribs_api.domains.tables.models import Attributes, Labels, Table, TableIn
from mpcontribs_api.exceptions import ConflictError, NotFoundError, PermissionError, ValidationError

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
            matrix=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
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


_MP_ID_REGISTRY: dict[str, str] = {}


def _mp_id_for(label: str) -> str:
    """Map an arbitrary test label onto a stable, valid ``material_id`` (``mp-<n>``).

    ``ContributionIn`` now validates ``material_id`` as ``mp-<digits>``, but these tests use
    readable labels (``"dup"``, ``"ok"``, ...) purely to mint identities. This preserves the
    pairing semantics they rely on — the same label always yields the same id (so intentional
    duplicates still collide) and distinct labels yield distinct ids — while producing a value the
    validator accepts. Values already shaped ``mp-<digits>`` pass through unchanged.
    """
    if label.startswith("mp-") and label[3:].isdigit():
        return label
    return _MP_ID_REGISTRY.setdefault(label, f"mp-{9_000_000 + len(_MP_ID_REGISTRY)}")


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
    material_id = _mp_id_for(material_id)
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
    bulk_write_limit: int = 1000,
) -> MongoSettings:
    return MongoSettings.model_validate({
        "uri": "mongodb://test",
        "db_name": "test",
        "max_pool_size": 100,
        "max_components_per_contribution": max_components_per_contribution,
        "max_concurrent_transactions": max_concurrent_transactions,
        "component_insert_chunk_size": component_insert_chunk_size,
        "bulk_write_limit": bulk_write_limit,
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
    projects=None,
    settings: MongoSettings | None = None,
    write_slots: asyncio.Semaphore | None = None,
    user: User | None = None,
    unique_column: str | None = None,
) -> tuple[ContributionService, AsyncMock, AsyncMock, AsyncMock, AsyncMock, MagicMock]:
    contrib_repo = contributions or AsyncMock()
    struct_repo = structures or AsyncMock()
    table_repo = tables or AsyncMock()
    attach_repo = attachments or AsyncMock()
    # ``coerce_identifiers`` is a *sync* repo method (see MongoDbRepository), but a bare AsyncMock
    # would turn it into a coroutine factory: the service passes its result straight into get_one/
    # patch_one without awaiting, leaking un-awaited coroutines. Make it a sync passthrough on every
    # repo so it behaves like the real thing (returns the identifiers dict unchanged).
    for repo in (contrib_repo, struct_repo, table_repo, attach_repo):
        repo.coerce_identifiers = MagicMock(side_effect=lambda identifiers: identifiers)
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


def _approved_projects_repo() -> AsyncMock:
    """A projects repo whose every project reads as approved (quota does not apply)."""
    repo = AsyncMock()
    repo.get_one = AsyncMock(return_value=MagicMock(is_approved=True))
    repo.unique_columns_by_id.side_effect = lambda ids: {pid: None for pid in ids}
    return repo


def _unapproved_projects_repo() -> AsyncMock:
    """A projects repo whose every project reads as unapproved (quota applies)."""
    repo = AsyncMock()
    repo.get_one = AsyncMock(return_value=MagicMock(is_approved=False))
    repo.unique_columns_by_id.side_effect = lambda ids: {pid: None for pid in ids}
    return repo


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
# insert_many — pre-checks (cheap, no DB)
# ---------------------------------------------------------------------------


class TestInsertContributionsPreChecks:
    async def test_empty_batch_returns_empty_summary_no_db(self):
        svc, contrib_repo, struct_repo, table_repo, attach_repo, client = _make_service()

        summary = await svc.insert_many([])

        assert summary.total == 0
        assert summary.succeeded == []
        assert summary.failed == []
        contrib_repo.insert_many.assert_not_called()
        contrib_repo.insert_one.assert_not_called()
        client.start_session.assert_not_called()

    async def test_duplicate_identity_in_one_batch_conflicts_later_item(self):
        """A repeated identity within one batch does not fail the whole request: the first occurrence
        is inserted; later intra-batch duplicates are per-item conflict failures."""
        svc, contrib_repo, _, _, _, client = _make_service()
        contrib_repo.insert_many.return_value = None
        contribs = [
            _contrib_in(project="prj", identifier="dup"),
            _contrib_in(project="prj", identifier="dup"),
        ]
        summary = await svc.insert_many(contribs)

        assert summary.total == 2
        assert len(summary.succeeded) == 1
        assert [f.index for f in summary.failed] == [1]
        assert summary.failed[0].error_code == "conflict"
        # Index 0 still reached Mongo (one doc inserted)
        assert len(contrib_repo.insert_many.call_args[0][0]) == 1

    async def test_oversize_contribution_goes_to_failures_without_db(self):
        settings = _make_mongo_settings(max_components_per_contribution=1)
        svc, contrib_repo, struct_repo, _, _, client = _make_service(settings=settings)
        contrib_repo.insert_many.return_value = None

        good = _contrib_in(identifier="ok")
        oversize = _contrib_in(identifier="big", structures=[_structure_in(), _structure_in()])

        summary = await svc.insert_many([good, oversize])

        assert summary.total == 2
        assert len(summary.failed) == 1
        assert summary.failed[0].index == 1
        assert summary.failed[0].error_code == "validation_error"
        # Oversize never reached the component repo
        struct_repo.insert_many.assert_not_called()
        # And the in-pool contribution did go through the no-component fast path
        contrib_repo.insert_many.assert_called_once()


# ---------------------------------------------------------------------------
# insert_many — unapproved-contribution quota
# ---------------------------------------------------------------------------


def _projects_repo_by_approval(approval: dict[str, bool]) -> AsyncMock:
    """Projects repo whose ``get_one`` reports approval per project id from ``approval``."""
    repo = AsyncMock()

    async def _get_one(identifiers, fields=None):
        return MagicMock(is_approved=approval[identifiers["id"]])

    repo.get_one = AsyncMock(side_effect=_get_one)
    repo.unique_columns_by_id.side_effect = lambda ids: {pid: None for pid in ids}
    return repo


class TestInsertContributionsUnapprovedQuota:
    async def test_unapproved_project_at_capacity_fails_all(self, monkeypatch):
        monkeypatch.setattr(get_settings().consumer, "max_unapproved_contributions_per_project", 2)
        contrib_repo = AsyncMock()
        contrib_repo.insert_many.return_value = None
        contrib_repo.count_contributions_for_project.return_value = 5  # already over cap
        svc, *_ = _make_service(contributions=contrib_repo, projects=_unapproved_projects_repo())

        summary = await svc.insert_many([_contrib_in(identifier=f"mp-{i}") for i in range(3)])

        assert summary.total == 3
        assert [f.index for f in summary.failed] == [0, 1, 2]
        assert all(f.error_code == "permission_denied" for f in summary.failed)
        assert summary.succeeded == []
        contrib_repo.insert_many.assert_not_called()

    async def test_batch_trimmed_to_remaining_capacity(self, monkeypatch):
        # cap 5, 3 already stored -> remaining = 5 - 3 = 2 slots for this batch
        monkeypatch.setattr(get_settings().consumer, "max_unapproved_contributions_per_project", 5)
        contrib_repo = AsyncMock()
        contrib_repo.insert_many.return_value = None
        contrib_repo.count_contributions_for_project.return_value = 3
        svc, *_ = _make_service(contributions=contrib_repo, projects=_unapproved_projects_repo())

        summary = await svc.insert_many([_contrib_in(identifier=f"mp-{i}") for i in range(4)])

        assert summary.total == 4
        assert len(summary.succeeded) == 2
        assert [f.index for f in summary.failed] == [2, 3]
        # Only the two accepted contributions reached the database
        inserted = contrib_repo.insert_many.call_args[0][0]
        assert len(inserted) == 2

    async def test_batch_may_fill_project_to_exactly_cap(self, monkeypatch):
        # cap 3, 2 stored -> exactly one slot; the batch fills the project to the cap, not past it.
        monkeypatch.setattr(get_settings().consumer, "max_unapproved_contributions_per_project", 3)
        contrib_repo = AsyncMock()
        contrib_repo.insert_many.return_value = None
        contrib_repo.count_contributions_for_project.return_value = 2
        svc, *_ = _make_service(contributions=contrib_repo, projects=_unapproved_projects_repo())

        summary = await svc.insert_many([_contrib_in(identifier=f"mp-{i}") for i in range(2)])

        assert summary.total == 2
        assert len(summary.succeeded) == 1
        assert [f.index for f in summary.failed] == [1]

    async def test_batch_at_exactly_cap_rejects_all_new(self, monkeypatch):
        # cap 3, 3 stored -> zero remaining slots; a project already at the cap admits nothing new.
        monkeypatch.setattr(get_settings().consumer, "max_unapproved_contributions_per_project", 3)
        contrib_repo = AsyncMock()
        contrib_repo.insert_many.return_value = None
        contrib_repo.count_contributions_for_project.return_value = 3
        svc, *_ = _make_service(contributions=contrib_repo, projects=_unapproved_projects_repo())

        summary = await svc.insert_many([_contrib_in(identifier=f"mp-{i}") for i in range(2)])

        assert [f.index for f in summary.failed] == [0, 1]
        assert summary.succeeded == []
        contrib_repo.insert_many.assert_not_called()

    async def test_approved_project_is_unlimited(self, monkeypatch):
        monkeypatch.setattr(get_settings().consumer, "max_unapproved_contributions_per_project", 1)
        contrib_repo = AsyncMock()
        contrib_repo.insert_many.return_value = None
        svc, *_ = _make_service(contributions=contrib_repo, projects=_approved_projects_repo())

        summary = await svc.insert_many([_contrib_in(identifier=f"mp-{i}") for i in range(3)])

        assert len(summary.succeeded) == 3
        assert summary.failed == []
        # Approved short-circuits before counting stored contributions
        contrib_repo.count_contributions_for_project.assert_not_called()

    async def test_quota_evaluated_per_project(self, monkeypatch):
        monkeypatch.setattr(get_settings().consumer, "max_unapproved_contributions_per_project", 2)
        contrib_repo = AsyncMock()
        contrib_repo.insert_many.return_value = None
        contrib_repo.count_contributions_for_project.return_value = 99  # only consulted for the unapproved one
        projects = _projects_repo_by_approval({"ok": True, "bad": False})
        svc, *_ = _make_service(contributions=contrib_repo, projects=projects)

        contribs = [
            _contrib_in(project="ok", identifier="a"),
            _contrib_in(project="bad", identifier="b"),
            _contrib_in(project="ok", identifier="c"),
        ]
        summary = await svc.insert_many(contribs)

        assert [f.index for f in summary.failed] == [1]
        assert len(summary.succeeded) == 2
        inserted_ids = {d.material_id for d in contrib_repo.insert_many.call_args[0][0]}
        assert inserted_ids == {_mp_id_for("a"), _mp_id_for("c")}

    async def test_breach_emits_structured_audit_log(self, monkeypatch):
        monkeypatch.setattr(get_settings().consumer, "max_unapproved_contributions_per_project", 2)
        contrib_repo = AsyncMock()
        contrib_repo.insert_many.return_value = None
        contrib_repo.count_contributions_for_project.return_value = 5
        svc, *_ = _make_service(contributions=contrib_repo, projects=_unapproved_projects_repo())

        with patch.object(service_module.logger, "warning") as warn:
            await svc.insert_many([_contrib_in(project="p", identifier=f"mp-{i}") for i in range(3)])

        warn.assert_called_once()
        event, kwargs = warn.call_args.args[0], warn.call_args.kwargs
        assert event == "contribution.unapproved_quota_exceeded"
        assert kwargs["project"] == "p"
        assert kwargs["max_allowed"] == 2
        assert kwargs["stored"] == 5
        assert kwargs["attempted"] == 3
        assert kwargs["accepted"] == 0
        assert kwargs["rejected"] == 3
        assert kwargs["rejected_identifiers"] == ["mp-0", "mp-1", "mp-2"]
        assert kwargs["rejected_identifiers_truncated"] is False

    async def test_approved_project_emits_no_audit_log(self, monkeypatch):
        monkeypatch.setattr(get_settings().consumer, "max_unapproved_contributions_per_project", 1)
        contrib_repo = AsyncMock()
        contrib_repo.insert_many.return_value = None
        svc, *_ = _make_service(contributions=contrib_repo, projects=_approved_projects_repo())

        with patch.object(service_module.logger, "warning") as warn:
            await svc.insert_many([_contrib_in(identifier=f"mp-{i}") for i in range(3)])

        warn.assert_not_called()


# ---------------------------------------------------------------------------
# upsert_many — unapproved-contribution quota (new docs only)
# ---------------------------------------------------------------------------


class TestUpsertContributionsUnapprovedQuota:
    async def test_only_new_documents_count_against_cap(self, monkeypatch):
        # cap 3, 2 stored -> one slot for a new document; updating an existing one is free.
        monkeypatch.setattr(get_settings().consumer, "max_unapproved_contributions_per_project", 3)
        contrib_repo = AsyncMock()
        contrib_repo.upsert_one.return_value = MagicMock(spec=Contribution, project="proj")
        contrib_repo.count_contributions_for_project.return_value = 2
        svc, *_ = _make_service(contributions=contrib_repo, projects=_unapproved_projects_repo())
        # Set after _make_service, which stubs existing_identities to an empty set. 'a' already exists.
        contrib_repo.existing_identities.return_value = {
            ContributionIdentity(
                project="proj", material_id=_mp_id_for("a"), chemical_system_id="Fe-O", formula="Fe2O3"
            )
        }

        contribs = [
            _contrib_in(identifier="a"),  # update of an existing contribution -> always allowed
            _contrib_in(identifier="b"),  # new -> consumes the one remaining slot
            _contrib_in(identifier="c"),  # new -> over cap, rejected
        ]
        summary = await svc.upsert_many(contribs)

        assert len(summary.succeeded) == 2
        assert [f.index for f in summary.failed] == [2]
        assert summary.failed[0].error_code == "permission_denied"
        upserted = {c.args[1].material_id for c in contrib_repo.upsert_one.call_args_list}
        assert upserted == {_mp_id_for("a"), _mp_id_for("b")}

    async def test_pure_updates_are_never_capped(self, monkeypatch):
        monkeypatch.setattr(get_settings().consumer, "max_unapproved_contributions_per_project", 1)
        contrib_repo = AsyncMock()
        contrib_repo.upsert_one.return_value = MagicMock(spec=Contribution, project="proj")
        contrib_repo.count_contributions_for_project.return_value = 99  # far over cap
        svc, *_ = _make_service(contributions=contrib_repo, projects=_unapproved_projects_repo())
        # Every contribution in the batch is an existing document -> all are free updates.
        contrib_repo.existing_identities.return_value = {
            ContributionIdentity(
                project="proj", material_id=f"mp-{i}", chemical_system_id="Fe-O", formula="Fe2O3"
            )
            for i in range(3)
        }

        summary = await svc.upsert_many([_contrib_in(identifier=f"mp-{i}") for i in range(3)])

        assert len(summary.succeeded) == 3
        assert summary.failed == []
        assert contrib_repo.upsert_one.call_count == 3

    async def test_approved_project_skips_quota(self, monkeypatch):
        monkeypatch.setattr(get_settings().consumer, "max_unapproved_contributions_per_project", 1)
        contrib_repo = AsyncMock()
        contrib_repo.upsert_one.return_value = MagicMock(spec=Contribution, project="proj")
        svc, *_ = _make_service(contributions=contrib_repo, projects=_approved_projects_repo())

        summary = await svc.upsert_many([_contrib_in(identifier=f"mp-{i}") for i in range(3)])

        assert len(summary.succeeded) == 3
        assert summary.failed == []
        contrib_repo.count_contributions_for_project.assert_not_called()
        contrib_repo.existing_identities.assert_not_called()


# ---------------------------------------------------------------------------
# upsert_one — single-record quota
# ---------------------------------------------------------------------------


class TestUpsertContributionByIdQuota:
    async def test_update_existing_allowed_even_over_cap(self, monkeypatch):
        monkeypatch.setattr(get_settings().consumer, "max_unapproved_contributions_per_project", 1)
        contrib_repo = AsyncMock()
        contrib_repo.get_one.return_value = MagicMock(spec=Contribution)  # id exists -> update
        contrib_repo.count_contributions_for_project.return_value = 99
        contrib_repo.upsert_one.return_value = MagicMock(spec=Contribution)
        svc, *_ = _make_service(contributions=contrib_repo, projects=_unapproved_projects_repo())

        await svc.upsert_one("someid", _contrib_in())

        contrib_repo.upsert_one.assert_called_once()
        contrib_repo.count_contributions_for_project.assert_not_called()

    async def test_new_insert_over_cap_rejected(self, monkeypatch):
        monkeypatch.setattr(get_settings().consumer, "max_unapproved_contributions_per_project", 2)
        contrib_repo = AsyncMock()
        contrib_repo.get_one.return_value = None  # id absent -> would insert
        contrib_repo.count_contributions_for_project.return_value = 5  # over cap
        svc, *_ = _make_service(contributions=contrib_repo, projects=_unapproved_projects_repo())

        with pytest.raises(PermissionError):
            await svc.upsert_one("someid", _contrib_in())

        contrib_repo.upsert_one.assert_not_called()

    async def test_new_insert_under_cap_allowed(self, monkeypatch):
        monkeypatch.setattr(get_settings().consumer, "max_unapproved_contributions_per_project", 5)
        contrib_repo = AsyncMock()
        contrib_repo.get_one.return_value = None
        contrib_repo.count_contributions_for_project.return_value = 1
        contrib_repo.upsert_one.return_value = MagicMock(spec=Contribution)
        svc, *_ = _make_service(contributions=contrib_repo, projects=_unapproved_projects_repo())

        await svc.upsert_one("someid", _contrib_in())

        contrib_repo.upsert_one.assert_called_once()

    async def test_new_insert_at_exactly_cap_rejected(self, monkeypatch):
        # stored == cap: the project is full, so a brand-new document is rejected (no cap+1 slack).
        monkeypatch.setattr(get_settings().consumer, "max_unapproved_contributions_per_project", 2)
        contrib_repo = AsyncMock()
        contrib_repo.get_one.return_value = None
        contrib_repo.count_contributions_for_project.return_value = 2
        svc, *_ = _make_service(contributions=contrib_repo, projects=_unapproved_projects_repo())

        with pytest.raises(PermissionError):
            await svc.upsert_one("someid", _contrib_in())

        contrib_repo.upsert_one.assert_not_called()

    async def test_new_insert_approved_project_unlimited(self, monkeypatch):
        monkeypatch.setattr(get_settings().consumer, "max_unapproved_contributions_per_project", 1)
        contrib_repo = AsyncMock()
        contrib_repo.get_one.return_value = None
        contrib_repo.upsert_one.return_value = MagicMock(spec=Contribution)
        svc, *_ = _make_service(contributions=contrib_repo, projects=_approved_projects_repo())

        await svc.upsert_one("someid", _contrib_in())

        contrib_repo.upsert_one.assert_called_once()
        contrib_repo.count_contributions_for_project.assert_not_called()


# ---------------------------------------------------------------------------
# insert_many — no-component fast path
# ---------------------------------------------------------------------------


class TestInsertContributionsNoComponentPath:
    async def test_all_no_components_uses_single_insert_many(self):
        svc, contrib_repo, _, _, _, client = _make_service()
        contrib_repo.insert_many.return_value = None

        contribs = [_contrib_in(identifier=f"mp-{i}") for i in range(3)]
        summary = await svc.insert_many(contribs)

        contrib_repo.insert_many.assert_called_once()
        # Zero transactions opened
        client.start_session.assert_not_called()
        contrib_repo.insert_one.assert_not_called()
        assert summary.total == 3
        assert len(summary.succeeded) == 3
        assert summary.failed == []

    async def test_is_public_forced_false_on_inserted_docs(self):
        svc, contrib_repo, _, _, _, _ = _make_service()
        contrib_repo.insert_many.return_value = None

        await svc.insert_many([_contrib_in()])

        docs = contrib_repo.insert_many.call_args[0][0]
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
        contrib_repo.insert_many.side_effect = bulk_err

        contribs = [_contrib_in(identifier=f"mp-{i}") for i in range(6)]
        summary = await svc.insert_many(contribs)

        assert summary.total == 6
        assert sorted(f.index for f in summary.failed) == [2, 5]
        assert all(f.error_code == "conflict" for f in summary.failed)
        # The 4 unaffected contributions succeed
        assert len(summary.succeeded) == 4


# ---------------------------------------------------------------------------
# insert_many — per-contribution transaction path
# ---------------------------------------------------------------------------


class TestInsertContributionsTransactionPath:
    async def test_with_components_opens_session_per_contribution(self):
        svc, contrib_repo, struct_repo, table_repo, attach_repo, client = _make_service()

        struct_repo.insert_many.return_value = [_fake_structure()]
        table_repo.insert_many.return_value = []
        attach_repo.insert_many.return_value = []

        async def _insert(doc, session=None):
            return doc

        contrib_repo.insert_one.side_effect = _insert

        contribs = [_contrib_in(identifier=f"c{i}", structures=[_structure_in()]) for i in range(3)]
        summary = await svc.insert_many(contribs)

        assert client.start_session.call_count == 3
        assert summary.total == 3
        assert len(summary.succeeded) == 3
        assert summary.failed == []

    async def test_session_threaded_to_all_repo_calls(self):
        client, session = _make_fake_client()
        svc, contrib_repo, struct_repo, table_repo, _, _ = _make_service(client=client)

        struct_repo.insert_many.return_value = [_fake_structure()]
        table_repo.insert_many.return_value = [_fake_table()]

        async def _insert(doc, session=None):
            return doc

        contrib_repo.insert_one.side_effect = _insert

        contrib = _contrib_in(
            structures=[_structure_in()],
            tables=[_table_in()],
            attachments=[_attachment_in()],
        )
        await svc.insert_many([contrib])
        assert struct_repo.insert_many.call_args.kwargs["session"] is session
        assert table_repo.insert_many.call_args.kwargs["session"] is session
        assert contrib_repo.insert_one.call_args.kwargs["session"] is session

    async def test_failure_on_second_of_three_yields_summary(self):
        svc, contrib_repo, struct_repo, table_repo, attach_repo, _ = _make_service()

        struct_repo.insert_many.return_value = [_fake_structure()]
        table_repo.insert_many.return_value = []
        attach_repo.insert_many.return_value = []

        async def _insert(doc, session=None):
            # Fail the second contribution by inspecting the doc's material_id
            if doc.material_id == _mp_id_for("fail"):
                raise ConflictError("conflict on insert")
            return doc

        contrib_repo.insert_one.side_effect = _insert

        contribs = [
            _contrib_in(identifier="ok-1", structures=[_structure_in()]),
            _contrib_in(identifier="fail", structures=[_structure_in()]),
            _contrib_in(identifier="ok-2", structures=[_structure_in()]),
        ]
        summary = await svc.insert_many(contribs)

        assert summary.total == 3
        assert len(summary.succeeded) == 2
        assert len(summary.failed) == 1
        assert summary.failed[0].index == 1
        assert summary.failed[0].error_code == "conflict"

    async def test_component_links_wired_per_contribution(self):
        svc, contrib_repo, struct_repo, table_repo, attach_repo, _ = _make_service()

        struct_a, struct_b = _fake_structure(), _fake_structure()
        struct_calls = iter([[struct_a], [struct_b]])
        struct_repo.insert_many.side_effect = lambda *_args, **_kwargs: next(struct_calls)
        table_repo.insert_many.return_value = []
        attach_repo.insert_many.return_value = []

        captured: list[Contribution] = []

        async def _insert(doc, session=None):
            captured.append(doc)
            return doc

        contrib_repo.insert_one.side_effect = _insert

        contribs = [
            _contrib_in(identifier="a", structures=[_structure_in()]),
            _contrib_in(identifier="b", structures=[_structure_in()]),
        ]
        await svc.insert_many(contribs)

        captured = {c.material_id: c for c in captured}
        assert captured[_mp_id_for("a")].structures == [struct_a]
        assert captured[_mp_id_for("b")].structures == [struct_b]

    async def test_pivoting_submission_shares_components_across_rows(self):
        svc, contrib_repo, struct_repo, table_repo, attach_repo, client = _make_service()

        shared = _fake_structure()
        struct_repo.insert_many.return_value = [shared]
        table_repo.insert_many.return_value = []
        attach_repo.insert_many.return_value = []

        captured: list[Contribution] = []

        async def _insert(doc, session=None):
            captured.append(doc)
            return doc

        contrib_repo.insert_one.side_effect = _insert

        # One submission that pivots into two rows (T=300K / T=400K) and carries a structure.
        contrib = _contrib_in(
            identifier="mp-1",
            data={"x (eV, T=300K)": 1, "x (eV, T=400K)": 2},
            structures=[_structure_in()],
        )
        summary = await svc.insert_many([contrib])

        # Components inserted once for the whole submission; both rows written in one transaction.
        assert struct_repo.insert_many.call_count == 1
        assert client.start_session.call_count == 1
        assert contrib_repo.insert_one.call_count == 2
        # Both pivoted rows link to the same shared structure and carry distinct condition keys.
        assert len(captured) == 2
        assert all(doc.structures == [shared] for doc in captured)
        assert len({doc.condition_key for doc in captured}) == 2
        # Summary is sized to the single submission but reports both pivoted rows as succeeded.
        assert summary.total == 1
        assert len(summary.succeeded) == 2
        assert summary.failed == []


# ---------------------------------------------------------------------------
# insert_many — mixed batch (partitioned across paths)
# ---------------------------------------------------------------------------


class TestInsertContributionsMixedBatch:
    async def test_mixed_batch_routes_correctly(self):
        svc, contrib_repo, struct_repo, table_repo, attach_repo, client = _make_service()

        struct_repo.insert_many.return_value = [_fake_structure()]
        table_repo.insert_many.return_value = []
        attach_repo.insert_many.return_value = []
        contrib_repo.insert_many.return_value = None

        async def _insert(doc, session=None):
            return doc

        contrib_repo.insert_one.side_effect = _insert

        contribs = [
            _contrib_in(identifier="bare-1"),
            _contrib_in(identifier="with-1", structures=[_structure_in()]),
            _contrib_in(identifier="bare-2"),
            _contrib_in(identifier="with-2", structures=[_structure_in()]),
        ]
        summary = await svc.insert_many(contribs)

        # No-component path: single batched call
        contrib_repo.insert_many.assert_called_once()
        assert len(contrib_repo.insert_many.call_args[0][0]) == 2
        # With-component path: one session per item
        assert client.start_session.call_count == 2
        assert contrib_repo.insert_one.call_count == 2
        assert summary.total == 4
        assert len(summary.succeeded) == 4
        assert summary.failed == []


# ---------------------------------------------------------------------------
# ContributionIdentity — uniqueness rules + unique_value resolution (insert & upsert)
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
        contrib_repo.insert_many.return_value = None
        contrib_repo.existing_identities.return_value = {
            ContributionIdentity(project="proj", material_id="mp-1", chemical_system_id="Fe-O", formula="Fe2O3")
        }

        summary = await svc.insert_many([_contrib_in(identifier="mp-1")])

        assert summary.total == 1
        assert summary.succeeded == []
        assert [f.error_code for f in summary.failed] == ["conflict"]
        contrib_repo.insert_many.assert_not_called()

    async def test_insert_no_existing_identity_succeeds(self):
        svc, contrib_repo, *_ = _make_service()
        contrib_repo.insert_many.return_value = None

        summary = await svc.insert_many([_contrib_in(identifier="mp-1")])

        assert len(summary.succeeded) == 1
        docs = contrib_repo.insert_many.call_args[0][0]
        assert docs[0].unique_value is None

    async def test_insert_unique_column_promotes_value_to_unique_value(self):
        svc, contrib_repo, *_ = _make_service(unique_column="sample_id")
        contrib_repo.insert_many.return_value = None

        summary = await svc.insert_many([_contrib_in(data={"sample_id": "A"})])

        assert len(summary.succeeded) == 1
        docs = contrib_repo.insert_many.call_args[0][0]
        assert docs[0].unique_value == "A"

    async def test_insert_same_triple_distinct_unique_value_both_succeed(self):
        svc, contrib_repo, *_ = _make_service(unique_column="sample_id")
        contrib_repo.insert_many.return_value = None

        contribs = [_contrib_in(data={"sample_id": "A"}), _contrib_in(data={"sample_id": "B"})]
        summary = await svc.insert_many(contribs)

        assert len(summary.succeeded) == 2
        docs = contrib_repo.insert_many.call_args[0][0]
        assert sorted(d.unique_value for d in docs) == ["A", "B"]

    async def test_insert_missing_unique_column_value_is_validation_failure(self):
        svc, contrib_repo, *_ = _make_service(unique_column="sample_id")
        contrib_repo.insert_many.return_value = None

        summary = await svc.insert_many([_contrib_in(data={"other": 1})])

        assert summary.succeeded == []
        assert [f.error_code for f in summary.failed] == ["validation_error"]
        contrib_repo.insert_many.assert_not_called()

    async def test_insert_non_scalar_unique_column_value_is_validation_failure(self):
        svc, contrib_repo, *_ = _make_service(unique_column="sample_id")
        contrib_repo.insert_many.return_value = None

        summary = await svc.insert_many([_contrib_in(data={"sample_id": {"nested": 1}})])

        assert summary.succeeded == []
        assert [f.error_code for f in summary.failed] == ["validation_error"]

    async def test_insert_empty_unique_column_dup_triple_conflicts(self):
        """With no unique_column, two contributions sharing the fixed-field triple collide."""
        svc, contrib_repo, *_ = _make_service()  # unique_column=None
        contrib_repo.insert_many.return_value = None

        contribs = [_contrib_in(identifier="mp-1"), _contrib_in(identifier="mp-1")]
        summary = await svc.insert_many(contribs)

        assert len(summary.succeeded) == 1
        assert [f.error_code for f in summary.failed] == ["conflict"]

    async def test_insert_project_not_found_is_validation_failure(self):
        svc, contrib_repo, *_ = _make_service(projects=_projects_mock({}))  # no projects known

        summary = await svc.insert_many([_contrib_in(identifier="mp-1")])

        assert summary.succeeded == []
        assert [f.error_code for f in summary.failed] == ["validation_error"]
        contrib_repo.insert_many.assert_not_called()

    async def test_upsert_does_not_conflict_on_existing_identity(self):
        """Upsert targets an existing identity (update), so it must not pre-reject as a conflict."""
        svc, contrib_repo, *_ = _make_service()
        contrib_repo.upsert_one.return_value = MagicMock(spec=Contribution, project="proj")

        await svc.upsert_many([_contrib_in(identifier="mp-1")])

        # existing_identities is not consulted on the upsert path
        contrib_repo.existing_identities.assert_not_called()
        contrib_repo.upsert_one.assert_called_once()

    async def test_upsert_passes_resolved_unique_value_in_identifiers(self):
        svc, contrib_repo, *_ = _make_service(unique_column="sample_id")
        contrib_repo.upsert_one.return_value = MagicMock(spec=Contribution, project="proj")

        await svc.upsert_many([_contrib_in(data={"sample_id": "A"})])

        identifiers = contrib_repo.upsert_one.call_args.args[0]
        assert identifiers["unique_value"] == "A"

    async def test_upsert_missing_unique_column_value_is_validation_failure(self):
        svc, contrib_repo, *_ = _make_service(unique_column="sample_id")

        summary = await svc.upsert_many([_contrib_in(data={"other": 1})])

        assert summary.succeeded == []
        assert [f.error_code for f in summary.failed] == ["validation_error"]
        assert "unique_column" in summary.failed[0].message
        contrib_repo.upsert_one.assert_not_called()


# ---------------------------------------------------------------------------
# upsert_many — guard clause
# ---------------------------------------------------------------------------


class TestUpsertContributionsGuard:
    async def test_raises_validation_error_when_any_contrib_has_structures(self):
        svc, *_ = _make_service()
        contrib = _contrib_in(structures=[_structure_in()])
        with pytest.raises(ValidationError):
            await svc.upsert_many([contrib])

    async def test_raises_validation_error_when_any_contrib_has_tables(self):
        svc, *_ = _make_service()
        contrib = _contrib_in(tables=[_table_in()])
        with pytest.raises(ValidationError):
            await svc.upsert_many([contrib])

    async def test_raises_validation_error_when_any_contrib_has_attachments(self):
        svc, *_ = _make_service()
        contrib = _contrib_in(attachments=[_attachment_in()])
        with pytest.raises(ValidationError):
            await svc.upsert_many([contrib])

    async def test_error_reports_indices_of_offending_contribs(self):
        svc, *_ = _make_service()
        clean = _contrib_in(identifier="clean")
        dirty = _contrib_in(identifier="dirty", structures=[_structure_in()])
        with pytest.raises(ValidationError) as exc_info:
            await svc.upsert_many([clean, dirty])
        assert exc_info.value.context.get("contribution_indices") == [1]

    async def test_multiple_offenders_all_indices_reported(self):
        svc, *_ = _make_service()
        contribs = [
            _contrib_in(identifier="c0", structures=[_structure_in()]),
            _contrib_in(identifier="c1"),
            _contrib_in(identifier="c2", tables=[_table_in()]),
        ]
        with pytest.raises(ValidationError) as exc_info:
            await svc.upsert_many(contribs)
        assert exc_info.value.context.get("contribution_indices") == [0, 2]

    async def test_raises_before_any_db_write(self):
        svc, contrib_repo, *_ = _make_service()
        dirty = _contrib_in(structures=[_structure_in()])
        with pytest.raises(ValidationError):
            await svc.upsert_many([dirty])
        contrib_repo.upsert_one.assert_not_called()
        contrib_repo.insert_one.assert_not_called()


# ---------------------------------------------------------------------------
# upsert_many — atomic dispatch
# ---------------------------------------------------------------------------


class TestUpsertContributionsAtomic:
    async def test_calls_atomic_repo_method_once_per_item(self):
        svc, contrib_repo, *_ = _make_service()
        contrib_repo.upsert_one.return_value = MagicMock(spec=Contribution, project="proj")

        contribs = [_contrib_in(identifier=f"mp-{i}") for i in range(3)]
        summary = await svc.upsert_many(contribs)

        assert summary.total == 3
        assert len(summary.succeeded) == 3
        assert summary.failed == []
        assert contrib_repo.upsert_one.call_count == 3
        # The atomic upsert path is used, not the bulk insert path.
        contrib_repo.insert_one.assert_not_called()

    async def test_passes_identifiers_dict_and_input_to_repo(self):
        svc, contrib_repo, *_ = _make_service()
        contrib_repo.upsert_one.return_value = MagicMock(spec=Contribution, project="proj")

        contrib = _contrib_in(project="my-proj", material_id="mp-99")
        await svc.upsert_many([contrib])

        call = contrib_repo.upsert_one.call_args
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
        for doc in docs:
            doc.project = "proj"  # real project so update_project can aggregate the affected set
        returned = {}

        async def _upsert(identifiers, contrib):
            doc = docs[int(contrib.material_id.split("-")[1])]
            returned[contrib.material_id] = doc
            return doc

        contrib_repo.upsert_one.side_effect = _upsert

        contribs = [_contrib_in(identifier=f"mp-{i}") for i in range(3)]
        summary = await svc.upsert_many(contribs)

        assert summary.succeeded == [returned["mp-0"], returned["mp-1"], returned["mp-2"]]

    async def test_empty_batch_returns_empty_summary(self):
        svc, contrib_repo, *_ = _make_service()
        summary = await svc.upsert_many([])
        assert summary.total == 0
        assert summary.succeeded == []
        assert summary.failed == []
        contrib_repo.upsert_one.assert_not_called()

    async def test_same_key_concurrent_upserts_both_go_through_atomic_call(self):
        """Race-safety regression: two items with the same (project, identifier) in one batch
        must both reach the atomic repo method. The repo (via the unique index) is the
        tiebreaker — the service must not pre-deduplicate or otherwise swallow one.
        """
        svc, contrib_repo, *_ = _make_service()
        contrib_repo.upsert_one.return_value = MagicMock(spec=Contribution, project="proj")

        contribs = [
            _contrib_in(project="prj", identifier="same"),
            _contrib_in(project="prj", identifier="same"),
        ]
        summary = await svc.upsert_many(contribs)

        assert len(summary.succeeded) == 2
        assert contrib_repo.upsert_one.call_count == 2

    async def test_one_failure_is_reported_not_raised(self):
        svc, contrib_repo, *_ = _make_service()

        async def _upsert(identifiers, contrib):
            if contrib.material_id == "mp-1":
                raise ConflictError("boom")
            return MagicMock(spec=Contribution, project="proj")

        contrib_repo.upsert_one.side_effect = _upsert

        contribs = [_contrib_in(identifier=f"mp-{i}") for i in range(3)]
        summary = await svc.upsert_many(contribs)

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
        contrib_repo.insert_many.return_value = None

        contribs = [
            _contrib_in(project="allowed", identifier="ok"),
            _contrib_in(project="forbidden", identifier="nope"),
        ]
        summary = await svc.insert_many(contribs)

        assert summary.total == 2
        assert len(summary.succeeded) == 1
        assert [f.index for f in summary.failed] == [1]
        assert summary.failed[0].error_code == "permission_denied"
        assert "forbidden" in summary.failed[0].message
        # Only the authorized item reached Mongo
        contrib_repo.insert_many.assert_called_once()

    async def test_insert_admin_bypasses_authorization(self):
        svc, contrib_repo, *_ = _make_service()  # default user is admin
        contrib_repo.insert_many.return_value = None

        contribs = [_contrib_in(project="anything", identifier=f"mp-{i}") for i in range(2)]
        summary = await svc.insert_many(contribs)

        assert summary.total == 2
        assert len(summary.succeeded) == 2
        assert summary.failed == []

    async def test_insert_unauthorized_and_oversize_yield_single_failure(self):
        """An item that is both unauthorized and oversize must produce exactly one BulkFailure
        (authorization runs first), preserving total == len(contributions)."""
        settings = _make_mongo_settings(max_components_per_contribution=1)
        svc, contrib_repo, struct_repo, _, _, _ = _make_service(user=_member_user("allowed"), settings=settings)

        bad = _contrib_in(project="forbidden", identifier="big", structures=[_structure_in(), _structure_in()])
        summary = await svc.insert_many([bad])

        assert summary.total == 1
        assert len(summary.failed) == 1
        assert summary.failed[0].index == 0
        assert summary.failed[0].error_code == "permission_denied"
        struct_repo.insert_many.assert_not_called()

    async def test_upsert_rejects_unauthorized_project_per_item(self):
        svc, contrib_repo, *_ = _make_service(user=_member_user("allowed"))
        contrib_repo.upsert_one.return_value = MagicMock(spec=Contribution, project="proj")

        contribs = [
            _contrib_in(project="allowed", identifier="ok"),
            _contrib_in(project="forbidden", identifier="nope"),
        ]
        summary = await svc.upsert_many(contribs)

        assert summary.total == 2
        assert len(summary.succeeded) == 1
        assert [f.index for f in summary.failed] == [1]
        assert summary.failed[0].error_code == "permission_denied"
        assert "forbidden" in summary.failed[0].message
        # Only the authorized item reached the atomic repo method
        contrib_repo.upsert_one.assert_called_once()

    async def test_upsert_anonymous_authorized_for_nothing(self):
        svc, contrib_repo, *_ = _make_service(user=User())  # anonymous: no username, no groups

        summary = await svc.upsert_many([_contrib_in(project="any", identifier="x")])

        assert summary.total == 1
        assert summary.succeeded == []
        assert [f.error_code for f in summary.failed] == ["permission_denied"]
        contrib_repo.upsert_one.assert_not_called()

    async def test_upsert_rejects_unauthorized_project(self):
        # A member of "allowed" cannot write "forbidden" through the by-id endpoint. The check runs
        # before any DB access, so neither the existence read nor the write is attempted — closing
        # the gap where the upsert's unscoped insert branch would create the contribution anyway.
        svc, contrib_repo, *_ = _make_service(user=_member_user("allowed"))

        with pytest.raises(PermissionError, match="forbidden"):
            await svc.upsert_one("someid", _contrib_in(project="forbidden"))

        contrib_repo.get_one.assert_not_called()
        contrib_repo.upsert_one.assert_not_called()

    async def test_upsert_unauthorized_cannot_overwrite_public_contribution(self):
        # Defense against overwriting a project's public contribution you don't own: even though the
        # repository read scope would admit a public row, authorization is enforced up front.
        svc, contrib_repo, *_ = _make_service(user=_member_user("allowed"))
        # An existing (readable) contribution must not lower the bar — authz still rejects the write.
        contrib_repo.get_one.return_value = MagicMock(spec=Contribution)

        with pytest.raises(PermissionError, match="forbidden"):
            await svc.upsert_one("someid", _contrib_in(project="forbidden"))

        contrib_repo.upsert_one.assert_not_called()

    async def test_upsert_anonymous_authorized_for_nothing(self):
        svc, contrib_repo, *_ = _make_service(user=User())  # anonymous: no username, no groups

        with pytest.raises(PermissionError):
            await svc.upsert_one("someid", _contrib_in(project="any"))

        contrib_repo.get_one.assert_not_called()
        contrib_repo.upsert_one.assert_not_called()

    async def test_upsert_authorized_member_proceeds(self):
        # A member writing to their own project passes authorization; updating an existing row is
        # not gated by the quota, so the write goes through.
        contrib_repo = AsyncMock()
        contrib_repo.get_one.return_value = MagicMock(spec=Contribution)  # exists -> update
        contrib_repo.upsert_one.return_value = MagicMock(spec=Contribution)
        svc, *_ = _make_service(
            contributions=contrib_repo, projects=_unapproved_projects_repo(), user=_member_user("allowed")
        )

        await svc.upsert_one("someid", _contrib_in(project="allowed"))

        contrib_repo.upsert_one.assert_called_once()

    async def test_upsert_admin_bypasses_authorization(self):
        contrib_repo = AsyncMock()
        contrib_repo.get_one.return_value = MagicMock(spec=Contribution)
        contrib_repo.upsert_one.return_value = MagicMock(spec=Contribution)
        svc, *_ = _make_service(contributions=contrib_repo, projects=_approved_projects_repo())  # admin default

        await svc.upsert_one("someid", _contrib_in(project="anything"))

        contrib_repo.upsert_one.assert_called_once()


# ---------------------------------------------------------------------------
# delete_many — cascade delete (components-first), cursor loop
# ---------------------------------------------------------------------------

from types import SimpleNamespace  # noqa: E402

from mpcontribs_api.domains._shared.models import DeleteResponse  # noqa: E402
from mpcontribs_api.domains.contributions.models import ContributionFilter  # noqa: E402
from mpcontribs_api.pagination import Page  # noqa: E402


def _link(ref_id: PydanticObjectId) -> SimpleNamespace:
    """Minimal stand-in for a Beanie Link: only ``.ref.id`` is read by the service."""
    return SimpleNamespace(ref=SimpleNamespace(id=ref_id))


def _contrib_doc(structures=None, attachments=None, tables=None, id_=None, project="proj") -> SimpleNamespace:
    """A contribution page item exposing the attributes delete_many reads."""
    return SimpleNamespace(
        id=id_ or _oid(),
        project=project,
        structures=[_link(s) for s in (structures or [])],
        attachments=[_link(a) for a in (attachments or [])],
        tables=[_link(t) for t in (tables or [])],
    )


def _page(items) -> Page:
    return Page(items=items, next_cursor=None)


def _delete_result(n: int) -> SimpleNamespace:
    """Stand-in for the delete result (only ``.num_deleted`` is read)."""
    return SimpleNamespace(num_deleted=n)


def _noop_filter() -> ContributionFilter:
    return ContributionFilter()


class TestDeleteContributionsEmpty:
    async def test_empty_match_returns_zero_summary(self):
        svc, contrib_repo, *_ = _make_service()
        contrib_repo.get_many.return_value = _page([])
        contrib_repo.delete_many.return_value = _delete_result(0)

        summary = await svc.delete_many(_noop_filter())

        assert summary.num_deleted == 0
        assert summary.num_children_deleted == 0

    async def test_empty_match_does_not_call_child_repos(self):
        svc, contrib_repo, struct_repo, table_repo, attach_repo, _ = _make_service()
        contrib_repo.get_many.return_value = _page([])
        contrib_repo.delete_many.return_value = _delete_result(0)

        await svc.delete_many(_noop_filter())

        struct_repo.delete_many.assert_not_called()
        table_repo.delete_many.assert_not_called()
        attach_repo.delete_many.assert_not_called()

    async def test_empty_match_terminates_after_one_page(self):
        svc, contrib_repo, *_ = _make_service()
        contrib_repo.get_many.return_value = _page([])
        contrib_repo.delete_many.return_value = _delete_result(0)

        await svc.delete_many(_noop_filter())

        assert contrib_repo.get_many.await_count == 1


class TestDeleteContributionsSinglePage:
    async def test_deletes_contributions_then_terminates(self):
        svc, contrib_repo, *_ = _make_service()
        docs = [_contrib_doc() for _ in range(3)]
        # First call returns the page; second returns empty so the loop ends.
        contrib_repo.get_many.side_effect = [_page(docs), _page([])]
        contrib_repo.delete_many.side_effect = [_delete_result(3), _delete_result(0)]

        summary = await svc.delete_many(_noop_filter())

        assert summary.num_deleted == 3

    async def test_no_components_means_no_child_deletes(self):
        svc, contrib_repo, struct_repo, table_repo, attach_repo, _ = _make_service()
        contrib_repo.get_many.side_effect = [_page([_contrib_doc()]), _page([])]
        contrib_repo.delete_many.side_effect = [_delete_result(1), _delete_result(0)]

        summary = await svc.delete_many(_noop_filter())

        struct_repo.delete_many.assert_not_called()
        table_repo.delete_many.assert_not_called()
        attach_repo.delete_many.assert_not_called()
        assert summary.num_children_deleted == 0

    async def test_components_deleted_before_contributions(self):
        # Records call order across repos to assert children go first.
        order: list[str] = []
        svc, contrib_repo, struct_repo, table_repo, attach_repo, _ = _make_service()

        doc = _contrib_doc(structures=[_oid()], tables=[_oid()], attachments=[_oid()])
        contrib_repo.get_many.side_effect = [_page([doc]), _page([])]

        def _make_child_recorder(name):
            async def _record(ids, *a, **k):
                order.append(name)
                return DeleteResponse(num_deleted=1)

            return _record

        struct_repo.delete_many.side_effect = _make_child_recorder("structures")
        table_repo.delete_many.side_effect = _make_child_recorder("tables")
        attach_repo.delete_many.side_effect = _make_child_recorder("attachments")

        async def _record_contrib(_filter, *a, **k):
            order.append("contributions")
            return _delete_result(1)

        contrib_repo.delete_many.side_effect = _record_contrib

        await svc.delete_many(_noop_filter())

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
        contrib_repo.get_many.side_effect = [_page([doc]), _page([])]
        struct_repo.delete_many.return_value = DeleteResponse(num_deleted=2)
        contrib_repo.delete_many.side_effect = [_delete_result(1), _delete_result(0)]

        await svc.delete_many(_noop_filter())

        called_filter = struct_repo.delete_many.await_args.args[0]
        assert set(called_filter.id__in) == {s1, s2}

    async def test_child_counts_accumulated_across_types(self):
        svc, contrib_repo, struct_repo, table_repo, attach_repo, _ = _make_service()
        doc = _contrib_doc(structures=[_oid()], tables=[_oid(), _oid()], attachments=[_oid()])
        contrib_repo.get_many.side_effect = [_page([doc]), _page([])]
        struct_repo.delete_many.return_value = DeleteResponse(num_deleted=1)
        table_repo.delete_many.return_value = DeleteResponse(num_deleted=2)
        attach_repo.delete_many.return_value = DeleteResponse(num_deleted=1)
        contrib_repo.delete_many.side_effect = [_delete_result(1), _delete_result(0)]

        summary = await svc.delete_many(_noop_filter())

        assert summary.num_children_deleted == 4

    async def test_contributions_deleted_in_of_page(self):
        svc, contrib_repo, *_ = _make_service()
        ids = [_oid(), _oid()]
        docs = [_contrib_doc(id_=i) for i in ids]
        contrib_repo.get_many.side_effect = [_page(docs), _page([])]
        contrib_repo.delete_many.side_effect = [_delete_result(2), _delete_result(0)]

        await svc.delete_many(_noop_filter())

        first_call_filter = contrib_repo.delete_many.await_args_list[0].args[0]
        assert set(first_call_filter.id__in) == set(ids)


class TestDeleteContributionsMultiPage:
    async def test_loops_until_page_empty(self):
        svc, contrib_repo, *_ = _make_service()
        contrib_repo.get_many.side_effect = [
            _page([_contrib_doc() for _ in range(2)]),
            _page([_contrib_doc()]),
            _page([]),
        ]
        contrib_repo.delete_many.side_effect = [
            _delete_result(2),
            _delete_result(1),
            _delete_result(0),
        ]

        summary = await svc.delete_many(_noop_filter())

        assert summary.num_deleted == 3
        assert contrib_repo.get_many.await_count == 3

    async def test_children_accumulate_across_pages(self):
        svc, contrib_repo, struct_repo, *_ = _make_service()
        contrib_repo.get_many.side_effect = [
            _page([_contrib_doc(structures=[_oid()])]),
            _page([_contrib_doc(structures=[_oid()])]),
            _page([]),
        ]
        struct_repo.delete_many.return_value = DeleteResponse(num_deleted=1)
        contrib_repo.delete_many.side_effect = [
            _delete_result(1),
            _delete_result(1),
            _delete_result(0),
        ]

        summary = await svc.delete_many(_noop_filter())

        assert summary.num_children_deleted == 2
        assert struct_repo.delete_many.await_count == 2


class TestDeleteContributionsNoneComponents:
    """ContributionOut leaves unset component fields as None (not []).

    The cascade loop must tolerate None rather than raising TypeError on iteration.
    """

    async def test_none_component_fields_do_not_raise(self):
        svc, contrib_repo, struct_repo, table_repo, attach_repo, _ = _make_service()
        doc = SimpleNamespace(id=_oid(), project="proj", structures=None, tables=None, attachments=None)
        contrib_repo.get_many.side_effect = [_page([doc]), _page([])]
        contrib_repo.delete_many.side_effect = [_delete_result(1), _delete_result(0)]

        summary = await svc.delete_many(_noop_filter())

        assert summary.num_deleted == 1
        assert summary.num_children_deleted == 0
        struct_repo.delete_many.assert_not_called()
        table_repo.delete_many.assert_not_called()
        attach_repo.delete_many.assert_not_called()


# ---------------------------------------------------------------------------
# patch_one — identifier hierarchy on the merged state
# ---------------------------------------------------------------------------


def _existing_doc(*, material_id, chemical_system_id, formula, project="proj"):
    """A stand-in for the persisted document that patch re-reads to validate the merged identity."""
    return SimpleNamespace(
        id=_oid(),
        project=project,
        material_id=material_id,
        chemical_system_id=chemical_system_id,
        formula=formula,
        data={},
    )


class TestPatchIdentifierHierarchy:
    async def test_patch_material_id_onto_doc_without_formula_raises(self):
        svc, contrib_repo, *_ = _make_service()
        existing = _existing_doc(material_id=None, chemical_system_id="Fe-O", formula=None)
        contrib_repo.get_one.return_value = existing

        with pytest.raises(ValidationError, match="formula is required when material_id"):
            await svc.patch_one(str(existing.id), ContributionPatch(material_id="mp-1"))

        # Rejected before any write.
        contrib_repo.patch_one.assert_not_called()

    async def test_patch_material_id_when_existing_has_formula_ok(self):
        svc, contrib_repo, *_ = _make_service()
        existing = _existing_doc(material_id=None, chemical_system_id="Fe-O", formula="Fe2O3")
        contrib_repo.get_one.return_value = existing
        contrib_repo.patch_one.return_value = MagicMock(spec=Contribution)

        await svc.patch_one(str(existing.id), ContributionPatch(material_id="mp-1"))

        contrib_repo.patch_one.assert_called_once()

    async def test_metadata_only_patch_skips_existing_read(self):
        svc, contrib_repo, *_ = _make_service()
        contrib_repo.patch_one.return_value = MagicMock(spec=Contribution)

        await svc.patch_one("some-id", ContributionPatch(is_public=True))

        # No identity/unique inputs touched -> no re-read, straight to the plain patch.
        contrib_repo.get_one.assert_not_called()
        contrib_repo.patch_one.assert_called_once()


# ---------------------------------------------------------------------------
# patch_one — data merge vs replace + unique_value resolution
# ---------------------------------------------------------------------------


class TestPatchDataMergeReplace:
    async def test_data_patch_defaults_to_merge_and_forwards_replace_false(self):
        svc, contrib_repo, *_ = _make_service()
        existing = _existing_doc(material_id=None, chemical_system_id="Fe-O", formula="Fe2O3")
        existing.data = {"x": 1.0}
        contrib_repo.get_one.return_value = existing
        contrib_repo.patch_one.return_value = MagicMock(spec=Contribution)

        await svc.patch_one(str(existing.id), ContributionPatch(data={"y": 9.0}))

        # The repo performs the actual dotted-$set merge; the service just forwards replace_data=False.
        assert contrib_repo.patch_one.call_args.kwargs["replace_data"] is False

    async def test_replace_data_flag_forwarded_to_repo(self):
        svc, contrib_repo, *_ = _make_service()
        existing = _existing_doc(material_id=None, chemical_system_id="Fe-O", formula="Fe2O3")
        existing.data = {"x": 1.0}
        contrib_repo.get_one.return_value = existing
        contrib_repo.patch_one.return_value = MagicMock(spec=Contribution)

        await svc.patch_one(
            str(existing.id), ContributionPatch(data={"y": 9.0}), replace_data=True
        )

        assert contrib_repo.patch_one.call_args.kwargs["replace_data"] is True

    async def test_merge_resolves_unique_value_from_merged_state(self):
        # The unique_column value lives in the stored data and is NOT in the patch. A merge preserves
        # it, so unique_value must resolve against the merged view rather than raising "missing".
        svc, contrib_repo, *_ = _make_service(unique_column="sample_id")
        existing = _existing_doc(material_id=None, chemical_system_id="Fe-O", formula="Fe2O3")
        existing.data = {"sample_id": 42, "x": 1.0}
        contrib_repo.get_one.return_value = existing
        contrib_repo.patch_one.return_value = MagicMock(spec=Contribution)

        await svc.patch_one(str(existing.id), ContributionPatch(data={"y": 9.0}))

        # Resolved from {sample_id:42, x:1, y:9}, so the untouched unique_value survives the merge.
        assert contrib_repo.patch_one.call_args.kwargs["unique_value"] == 42

    async def test_replace_resolves_unique_value_from_patch_data_only(self):
        # On replace the stored data is discarded, so a unique_column absent from the patch is a
        # genuine validation failure (the resulting document would lack it).
        svc, contrib_repo, *_ = _make_service(unique_column="sample_id")
        existing = _existing_doc(material_id=None, chemical_system_id="Fe-O", formula="Fe2O3")
        existing.data = {"sample_id": 42}
        contrib_repo.get_one.return_value = existing

        with pytest.raises(ValidationError, match="unique_column"):
            await svc.patch_one(
                str(existing.id), ContributionPatch(data={"y": 9.0}), replace_data=True
            )
        contrib_repo.patch_one.assert_not_called()
