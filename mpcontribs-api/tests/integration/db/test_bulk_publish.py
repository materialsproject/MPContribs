import pytest

from mpcontribs_api.authz import User
from mpcontribs_api.domains.attachments.repository import MongoDbAttachmentRepository
from mpcontribs_api.domains.contributions.models import (
    Contribution,
    ContributionBulkUpdate,
    ContributionFilter,
    ContributionIn,
    ContributionPatch,
)
from mpcontribs_api.domains.contributions.repository import MongoDbContributionRepository
from mpcontribs_api.domains.contributions.service import ContributionService
from mpcontribs_api.domains.projects.repository import MongoDbProjectRepository
from mpcontribs_api.domains.structures.repository import MongoDbStructureRepository
from mpcontribs_api.domains.tables.repository import MongoDbTableRepository

pytestmark = [pytest.mark.db, pytest.mark.asyncio(loop_scope="session")]

# ALICE may write only PROJ_A; PROJ_B is foreign to her. ADMIN may write anything.
ALICE = User(username="google:alice@example.com", groups=frozenset({"proj-a"}))
ADMIN = User(username="google:admin@example.com", groups=frozenset({"admin"}))
PROJ_A = "proj-a"
PROJ_B = "proj-b"


def _service(client, user: User) -> ContributionService:
    """A ContributionService wired exactly like the FastAPI dependency, for ``user``."""
    return ContributionService(
        client=client,
        user=user,
        projects=MongoDbProjectRepository(user),
        contributions=MongoDbContributionRepository(user),
        structures=MongoDbStructureRepository(user),
        attachments=MongoDbAttachmentRepository(user),
        tables=MongoDbTableRepository(user),
    )


async def _insert(project: str, identifier: str, *, is_public: bool) -> Contribution:
    """Insert one contribution directly (bypassing the write pipeline) with a chosen visibility.

    ``identifier`` is a human label only; each case here uses a distinct project, so the identity
    tuple (project + chemical_system_id + formula) is unique without a material_id.
    """
    doc = Contribution.from_input_model(
        ContributionIn(project=project, chemical_system_id="Fe-O", formula="Fe2O3", data={"x": 1.0})
    )
    doc.is_public = is_public
    await doc.insert()
    return doc


async def _is_public(cid) -> bool:
    found = await Contribution.find_one(Contribution.id == cid)
    assert found is not None
    return found.is_public


class TestBulkPublishAuthorization:
    async def test_publishes_only_writable_projects(self, db, mongo_client):
        # Alice's own project is private-but-writable; the foreign project is out of her write scope.
        a = await _insert(PROJ_A, "c1", is_public=False)
        b = await _insert(PROJ_B, "c1", is_public=False)

        summary = await _service(mongo_client, ALICE).bulk_update(
            ContributionFilter(), ContributionBulkUpdate(is_public=True)
        )

        assert summary.projects == [PROJ_A]
        assert (summary.matched, summary.modified) == (1, 1)
        assert await _is_public(a.id) is True
        assert await _is_public(b.id) is False  # foreign project untouched

    async def test_public_in_other_project_not_modified(self, db, mongo_client):
        # A public contribution in a foreign project is *readable* by Alice (scope), but the bulk
        # update constrains to writable projects, so a filter matching it modifies nothing.
        b = await _insert(PROJ_B, "pub", is_public=True)

        summary = await _service(mongo_client, ALICE).bulk_update(
            ContributionFilter(is_public=True), ContributionBulkUpdate(is_public=False)
        )

        assert (summary.matched, summary.modified) == (0, 0)
        assert summary.projects == []
        assert await _is_public(b.id) is True  # still public

    async def test_admin_is_unconstrained_by_project(self, db, mongo_client):
        a = await _insert(PROJ_A, "c1", is_public=False)
        b = await _insert(PROJ_B, "c1", is_public=False)

        summary = await _service(mongo_client, ADMIN).bulk_update(
            ContributionFilter(), ContributionBulkUpdate(is_public=True)
        )

        assert set(summary.projects) == {PROJ_A, PROJ_B}
        assert (summary.matched, summary.modified) == (2, 2)
        assert await _is_public(a.id) is True
        assert await _is_public(b.id) is True


class TestSinglePublish:
    async def test_patch_by_id_publishes_single_contribution(self, db, mongo_client):
        a = await _insert(PROJ_A, "c1", is_public=False)

        result = await _service(mongo_client, ALICE).patch_contribution_by_id(
            str(a.id), ContributionPatch(is_public=True)
        )

        assert result.is_public is True
        assert await _is_public(a.id) is True
