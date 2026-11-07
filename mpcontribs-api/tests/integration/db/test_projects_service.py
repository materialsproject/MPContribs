import pytest

from mpcontribs_api.authz import User
from mpcontribs_api.domains.projects.models import Project, ProjectFilter
from mpcontribs_api.domains.projects.repository import MongoDbProjectRepository
from mpcontribs_api.domains.projects.service import ProjectService
from mpcontribs_api.pagination import CursorParams

pytestmark = [pytest.mark.db, pytest.mark.asyncio(loop_scope="session")]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
# Projects are read-only through the API (writes flow through /uploads). These tests cover the
# service's read surface and the repository read scope it enforces.

ADMIN = User(username="google:admin@example.com", groups=frozenset({"admin"}))
ALICE = User(username="google:alice@example.com", groups=frozenset({"mp-team"}))
BOB = User(username="google:bob@example.com", groups=frozenset())

ALICE_EMAIL = "google:alice@example.com"


def _service(user: User) -> ProjectService:
    return ProjectService(projects=MongoDbProjectRepository(user))


async def _insert(id: str, **overrides) -> Project:
    """Seed a project directly (admin, no policy) — construct the stored document by hand."""
    fields = {
        "title": id[:30],
        "authors": "Test Author",
        "description": "Test description",
        "owner": ALICE_EMAIL,
    }
    fields.update(overrides)
    return await MongoDbProjectRepository(ADMIN).insert_one(Project(_id=id, **fields))


# ---------------------------------------------------------------------------
# Read scope — GET "" and GET /{id} filter by user visibility
# ---------------------------------------------------------------------------


class TestReadScope:
    async def test_get_many_hides_private_unowned(self, db):
        # Alice owns one public+approved project and one private one. Bob (no roles) sees only the
        # public+approved one; Alice's private project must not leak into his listing.
        await _insert("scope-pub", owner=ALICE_EMAIL, is_public=True, is_approved=True)
        await _insert("scope-priv", owner=ALICE_EMAIL, is_public=False)
        page = await _service(BOB).read_many(filter=ProjectFilter(), pagination=CursorParams(), fields=None)
        ids = {p.id for p in page.items}
        assert "scope-pub" in ids
        assert "scope-priv" not in ids

    async def test_get_one_private_unowned_returns_none(self, db):
        await _insert("scope-one-priv", owner=ALICE_EMAIL, is_public=False)
        assert await _service(BOB).read_one({"id": "scope-one-priv"}, fields=None) is None

    async def test_get_one_public_visible_to_non_owner(self, db):
        await _insert("scope-one-pub", owner=ALICE_EMAIL, is_public=True, is_approved=True)
        found = await _service(BOB).read_one({"id": "scope-one-pub"}, fields=None)
        assert found is not None and found.id == "scope-one-pub"

    async def test_owner_sees_own_private_project(self, db):
        await _insert("scope-own-priv", owner=ALICE_EMAIL, is_public=False)
        found = await _service(ALICE).read_one({"id": "scope-own-priv"}, fields=None)
        assert found is not None and found.id == "scope-own-priv"
