import pytest
from beanie import PydanticObjectId

from mpcontribs_api.authz import User
from mpcontribs_api.authz_core import ReservedRole
from mpcontribs_api.domains.structures.models import Structure
from mpcontribs_api.domains.structures.repository import MongoDbStructureRepository

pytestmark = [pytest.mark.db, pytest.mark.asyncio(loop_scope="session")]


# ---------------------------------------------------------------------------
# Thin, content-addressed structure index: content lives in S3 (always the latest object); Mongo holds
# only (project, hash, size, ext), keyed by its content-addressed (project, hash) location. These
# exercise the index round-trip and that reads go through the component repository.
# ---------------------------------------------------------------------------

HASH_A = "a" * 64
HASH_B = "b" * 64


def _structure(hash: str = HASH_A, size: int = 2048, project: str = "my_project", ext: str = "cif") -> Structure:
    return Structure.model_validate(
        {"_id": PydanticObjectId(), "project": project, "hash": hash, "size": size, "ext": ext}
    )


def _repo() -> MongoDbStructureRepository:
    return MongoDbStructureRepository(User(username="admin", groups=[ReservedRole.admin]))


class TestIndexRoundTrip:
    async def test_thin_document_survives_insert_and_read(self, db):
        doc = _structure(hash=HASH_A, size=4096)
        await doc.insert()

        read = await Structure.get(doc.id)
        assert read is not None
        assert read.project == "my_project"
        assert read.hash == HASH_A
        assert read.size == 4096
        assert read.ext == "cif"

    async def test_read_one_by_project_and_hash(self, db):
        doc = _structure(hash=HASH_A)
        await doc.insert()
        found = await _repo().read_one({"project": "my_project", "hash": HASH_A}, fields=None)
        assert found is not None
        assert found.id == doc.id

    async def test_distinct_hashes_coexist(self, db):
        a = _structure(hash=HASH_A, size=100)
        b = _structure(hash=HASH_B, size=120)
        await a.insert()
        await b.insert()

        both = await Structure.find(Structure.project == "my_project").to_list()
        assert {d.hash for d in both} == {HASH_A, HASH_B}
