"""End-to-end cascade deletion against a real MongoDB.

Deleting a project removes every contribution under it, and each contribution removes its
components (structures/attachments) — but **only when valid**: a component that a *surviving*
contribution still references is kept, so no live contribution is left with a dangling link.
Components are md5-deduplicated, so this shared-reference case is real.

These tests drive the real ``ProjectService``/``ContributionService`` against Mongo. Contribution
documents are built directly (so a single component can be shared across several of them) mirroring
``test_component_reachability.py``. Tables are intentionally avoided in the delete path — see
``test_stats_recompute.py`` for the pre-existing ``Table.data`` round-trip bug; structures and
attachments exercise the same cascade.
"""

from typing import cast

import pytest
from beanie import PydanticObjectId
from pymatgen.core import Element
from pymongo import AsyncMongoClient

from mpcontribs_api.authz import User
from mpcontribs_api.domains.attachments.models import Attachment
from mpcontribs_api.domains.attachments.repository import MongoDbAttachmentRepository
from mpcontribs_api.domains.contributions.models import Contribution, ContributionFilter
from mpcontribs_api.domains.contributions.repository import MongoDbContributionRepository
from mpcontribs_api.domains.contributions.service import ContributionService
from mpcontribs_api.domains.initiatives.repository import MongoDbInitiativeRepository
from mpcontribs_api.domains.projects.models import Project, ProjectIn
from mpcontribs_api.domains.projects.repository import MongoDbProjectRepository
from mpcontribs_api.domains.projects.service import ProjectService
from mpcontribs_api.domains.structures.models import Lattice, Site, SiteProperties, Species, Structure, StructureIn
from mpcontribs_api.domains.structures.repository import MongoDbStructureRepository
from mpcontribs_api.domains.tables.repository import MongoDbTableRepository

pytestmark = [pytest.mark.db, pytest.mark.asyncio(loop_scope="session")]

ADMIN = User(username="google:admin@example.com", groups=frozenset({"admin"}))


# ---------------------------------------------------------------------------
# Service builders (wired exactly like the FastAPI dependencies)
# ---------------------------------------------------------------------------


def _contribution_service(client: AsyncMongoClient, user: User = ADMIN) -> ContributionService:
    return ContributionService(
        client=client,
        user=user,
        projects=MongoDbProjectRepository(user),
        contributions=MongoDbContributionRepository(user),
        structures=MongoDbStructureRepository(user),
        attachments=MongoDbAttachmentRepository(user),
        tables=MongoDbTableRepository(user),
    )


def _project_service(client: AsyncMongoClient, user: User = ADMIN) -> ProjectService:
    return ProjectService(
        user=user,
        projects=MongoDbProjectRepository(user),
        initiatives=MongoDbInitiativeRepository(user),
        contribution_service=_contribution_service(client, user),
    )


# ---------------------------------------------------------------------------
# Document builders
# ---------------------------------------------------------------------------


async def _project(id: str, owner: str = ADMIN.username or "") -> Project:
    project_in = ProjectIn(title=id[:30], authors="Test Author", description="cascade fixture", owner=owner)
    return await MongoDbProjectRepository(ADMIN).insert_one(Project.from_input_model(project_in, id=id))


def _structure_in(charge: float) -> StructureIn:
    """A valid structure; ``charge`` is a hash field, so distinct values yield distinct md5 (no dedup)."""
    return StructureIn(
        name="struct",
        lattice=Lattice(
            matrix=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
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


async def _structure(charge: float) -> Structure:
    doc = Structure.from_input(_structure_in(charge))
    await doc.insert()
    return doc


async def _attachment(content: int) -> Attachment:
    # md5 is server-computed from (mime, content); distinct content -> distinct md5/dedup.
    doc = Attachment(_id=PydanticObjectId(), name="d.csv", mime="application/gzip", content=content)
    await doc.insert()
    return doc


async def _contribution(
    project: str,
    material_id: str,
    *,
    structures: list[Structure] | None = None,
    attachments: list[Attachment] | None = None,
) -> Contribution:
    doc = Contribution(
        _id=PydanticObjectId(),
        project=project,
        material_id=material_id,
        chemical_system_id="Fe-O",
        formula="Fe2O3",
        data={"x": 1},
        is_public=False,
        structures=structures or [],
        attachments=attachments or [],
    )
    await doc.insert()
    return doc


async def _structure_exists(doc: Structure) -> bool:
    return await Structure.find_one(Structure.id == doc.id) is not None


# ---------------------------------------------------------------------------
# Project delete -> contributions -> components
# ---------------------------------------------------------------------------


class TestProjectDeleteCascade:
    async def test_deletes_project_contributions_and_unshared_components(self, db, mongo_client):
        await _project("cas-full")
        s1, s2 = await _structure(1.0), await _structure(2.0)
        a1 = await _attachment(1)
        await _contribution("cas-full", "mp-a", structures=[s1], attachments=[a1])
        await _contribution("cas-full", "mp-b", structures=[s2])

        summary = await _project_service(mongo_client).delete_one({"id": "cas-full"})

        assert summary.root == {"projects": 1, "contributions": 2, "structures": 2, "attachments": 1}
        assert await Project.find_one(Project.id == "cas-full") is None
        assert await Contribution.find(Contribution.project == "cas-full").count() == 0
        assert not await _structure_exists(s1)
        assert not await _structure_exists(s2)
        assert await Attachment.find_one(Attachment.id == a1.id) is None

    async def test_empty_project_deletes_with_no_cascade(self, db, mongo_client):
        await _project("cas-empty")

        summary = await _project_service(mongo_client).delete_one({"id": "cas-empty"})

        assert summary.root == {"projects": 1}

    async def test_component_shared_with_surviving_project_is_kept(self, db, mongo_client):
        # ``shared`` is referenced by a contribution in the deleted project *and* one in a project
        # that survives; ``only_here`` is referenced solely by the deleted project.
        await _project("cas-doomed")
        await _project("cas-survivor")
        shared = await _structure(10.0)
        only_here = await _structure(11.0)
        await _contribution("cas-doomed", "mp-x", structures=[shared, only_here])
        survivor = await _contribution("cas-survivor", "mp-y", structures=[shared])

        summary = await _project_service(mongo_client).delete_one({"id": "cas-doomed"})

        # Only the unshared structure is removed; the shared one is kept.
        assert summary.root == {"projects": 1, "contributions": 1, "structures": 1}
        assert not await _structure_exists(only_here)
        assert await _structure_exists(shared)
        # The surviving contribution is untouched and still links the shared structure.
        reloaded = await Contribution.get(survivor.id)
        assert reloaded is not None
        assert [link.ref.id for link in (reloaded.structures or [])] == [shared.id]


# ---------------------------------------------------------------------------
# Contribution delete -> components, valid or not
# ---------------------------------------------------------------------------


class TestContributionDeleteCascade:
    async def test_component_shared_by_sibling_contribution_is_kept(self, db, mongo_client):
        await _project("cas-sib")
        shared = await _structure(20.0)
        only_a = await _structure(21.0)
        a = await _contribution("cas-sib", "mp-a", structures=[shared, only_a])
        await _contribution("cas-sib", "mp-b", structures=[shared])

        summary = await _contribution_service(mongo_client).delete_one({"id": str(a.id)})

        assert summary.root == {"contributions": 1, "structures": 1}
        assert not await _structure_exists(only_a)
        assert await _structure_exists(shared)  # sibling ``mp-b`` still references it
        assert await Contribution.get(a.id) is None

    async def test_component_referenced_only_by_deleted_contribution_is_removed(self, db, mongo_client):
        await _project("cas-solo")
        only = await _structure(30.0)
        a = await _contribution("cas-solo", "mp-a", structures=[only])

        summary = await _contribution_service(mongo_client).delete_one({"id": str(a.id)})

        assert summary.root == {"contributions": 1, "structures": 1}
        assert not await _structure_exists(only)

    async def test_two_deleted_contributions_sharing_a_component_remove_it(self, db, mongo_client):
        # Both referencing contributions are in the delete set, so nothing survives to keep the
        # shared structure alive — it must be removed.
        await _project("cas-both")
        shared = await _structure(40.0)
        await _contribution("cas-both", "mp-a", structures=[shared])
        await _contribution("cas-both", "mp-b", structures=[shared])

        summary = await _contribution_service(mongo_client).delete_many(ContributionFilter(project="cas-both"))

        assert summary.root == {"contributions": 2, "structures": 1}
        assert not await _structure_exists(shared)
