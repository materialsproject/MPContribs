import pytest
from beanie import PydanticObjectId

from mpcontribs_api.authz import User
from mpcontribs_api.authz_core import ReservedRole
from mpcontribs_api.domains.structures.models import Structure
from mpcontribs_api.domains.structures.repository import MongoDbStructureRepository

pytestmark = [pytest.mark.db, pytest.mark.asyncio(loop_scope="session")]


# ---------------------------------------------------------------------------
# Thin, S3-versioned structure index: content lives in S3; Mongo holds only
# (name, s3_version_id, size) per version. These exercise the index round-trip
# and the ``size_stats`` aggregation used for project stats.
# ---------------------------------------------------------------------------


def _structure(
    name: str = "relaxed-cell", s3_version_id: str = "v-1", size: int = 2048, project: str = "my_project"
) -> Structure:
    return Structure.model_validate(
        {"_id": PydanticObjectId(), "project": project, "name": name, "s3_version_id": s3_version_id, "size": size}
    )


def _repo() -> MongoDbStructureRepository:
    return MongoDbStructureRepository(User(username="admin", groups=[ReservedRole.admin]))


class TestIndexRoundTrip:
    async def test_thin_document_survives_insert_and_read(self, db):
        doc = _structure(name="Fe2O3", s3_version_id="v-abc", size=4096)
        await doc.insert()

        read = await Structure.get(doc.id)
        assert read is not None
        assert read.name == "Fe2O3"
        assert read.s3_version_id == "v-abc"
        assert read.size == 4096

    async def test_same_name_different_version_coexist(self, db):
        # A lineage is ``(project-key) name``; successive uploads are distinct versions (distinct docs).
        v1 = _structure(name="cell", s3_version_id="v-1", size=100)
        v2 = _structure(name="cell", s3_version_id="v-2", size=120)
        await v1.insert()
        await v2.insert()

        both = await Structure.find(Structure.name == "cell").to_list()
        assert {d.s3_version_id for d in both} == {"v-1", "v-2"}


class TestSizeStats:
    async def test_sums_sizes_of_given_versions(self, db):
        a = _structure(name="a", s3_version_id="va", size=100)
        b = _structure(name="b", s3_version_id="vb", size=250)
        await a.insert()
        await b.insert()

        total = await _repo().size_stats([a.id, b.id])
        assert total == 350

    async def test_empty_ids_is_zero(self, db):
        assert await _repo().size_stats([]) == 0
