"""Fixtures for tests that require a live MongoDB connection.

Connection settings come from the .env file (MPCONTRIBS_MONGO__URI and
MPCONTRIBS_MONGO__DB_NAME).  All tests in this directory are marked `db`
automatically; run them with `just test db` or skip them with `-m "not db"`.

Data isolation: the `clean_projects` and `clean_contributions` fixtures
(autouse) delete all documents from the test collections before each test.
This is intentionally destructive — point MPCONTRIBS_MONGO__DB_NAME at a
dedicated test database, not a shared or production one.
"""

import pytest
import pytest_asyncio
from beanie import init_beanie
from pymongo import AsyncMongoClient

from src.mpcontribs_api.config import get_settings
from src.mpcontribs_api.domains.contributions.models import Contribution
from src.mpcontribs_api.domains.projects.models import Project

# ---------------------------------------------------------------------------
# Auto-mark all tests in this directory as @pytest.mark.db
# ---------------------------------------------------------------------------

pytestmark = [
    pytest.mark.db,
    pytest.mark.asyncio(loop_scope="session"),
]


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
    # Only initialise concrete documents (stubs like Structure/Table/Attachment
    # have no Settings.name yet and cause Beanie to fall back to the base class).
    await init_beanie(
        database=database,
        document_models=[Project, Contribution],
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
