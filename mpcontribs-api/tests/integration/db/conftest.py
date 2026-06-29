import pytest
import pytest_asyncio
from beanie import init_beanie
from pymongo import AsyncMongoClient

from mpcontribs_api.config import get_settings
from mpcontribs_api.domains.attachments.models import Attachment
from mpcontribs_api.domains.contributions.models import Contribution
from mpcontribs_api.domains.projects.models import Project
from mpcontribs_api.domains.structures.models import Structure
from mpcontribs_api.domains.tables.models import Table

# ---------------------------------------------------------------------------
# Auto-mark all tests in this directory as @pytest.mark.db
# ---------------------------------------------------------------------------

pytestmark = [
    pytest.mark.db,
    pytest.mark.asyncio(loop_scope="session"),
]


@pytest.fixture(scope="session")
def _mock_beanie_collection():
    """Override the parent integration conftest's Beanie mock.

    DB tests initialise Beanie for real via init_beanie(), so the mock must not
    intercept get_pymongo_collection().  Defining this fixture here (same name,
    no patch) causes pytest to use this no-op instead of the parent's version.
    """
    yield


def pytest_collection_modifyitems(items):
    for item in items:
        if "integration/db" in str(item.fspath):
            item.add_marker(pytest.mark.db)
            item.add_marker(pytest.mark.asyncio(loop_scope="session"))


# ---------------------------------------------------------------------------
# Session-scoped MongoDB connection + Beanie initialization
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="session")
async def mongo_client():
    """Connect to the Atlas dev instance; skip if unreachable."""
    settings = get_settings()
    client = AsyncMongoClient(
        settings.mongo.uri.get_secret_value(),
        serverSelectionTimeoutMS=5_000,
    )
    try:
        await client.admin.command("ping")
    except Exception as exc:
        pytest.skip(f"MongoDB not reachable: {exc}")
    yield client
    await client.close()


@pytest_asyncio.fixture(scope="session")
async def db(mongo_client):
    """Database handle with Beanie initialised against the test database."""
    settings = get_settings()
    database = mongo_client[settings.mongo.db_name]
    await init_beanie(
        database=database,
        document_models=[Project, Contribution, Structure, Table, Attachment],
    )
    yield database


# ---------------------------------------------------------------------------
# Per-test collection cleanup  (autouse so every test starts clean)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(autouse=True)
async def clean_projects(db):
    await db["projects"].delete_many({})
    yield
    await db["projects"].delete_many({})


@pytest_asyncio.fixture(autouse=True)
async def clean_contributions(db):
    await db["contributions"].delete_many({})
    yield
    await db["contributions"].delete_many({})


@pytest_asyncio.fixture(autouse=True)
async def clean_components(db):
    for collection in ("structures", "tables", "attachments"):
        await db[collection].delete_many({})
    yield
    for collection in ("structures", "tables", "attachments"):
        await db[collection].delete_many({})
