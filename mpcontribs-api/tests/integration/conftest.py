from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mpcontribs_api.exceptions import register_exception_handlers
from mpcontribs_api.middleware import RequestContextMiddleware


@pytest.fixture(autouse=True, scope="session")
def _mock_beanie_collection():
    """Stub Beanie's collection check for mock-based integration tests.

    FastAPI parses request bodies into Beanie Document subclasses (e.g.
    ProjectIn), which calls get_pymongo_collection() in __init__.  Without a
    real init_beanie() these raise CollectionWasNotInitialized.

    The tests/integration/db/ conftest overrides this fixture with a no-op so
    DB tests still get the real Beanie collection after init_beanie().
    """
    import beanie

    with patch.object(beanie.Document, "get_pymongo_collection", return_value=MagicMock()):
        yield

# ---------------------------------------------------------------------------
# Header constants used across test modules
# ---------------------------------------------------------------------------

from mpcontribs_api.config import get_settings

ANON_HEADERS: dict[str, str] = {}

AUTHED_HEADERS = {
    "x-consumer-username": "google:alice@example.com",
    "x-consumer-id": "test-consumer-id",
    "x-authenticated-groups": "mp-team",
}

ADMIN_HEADERS = {
    "x-consumer-username": "google:admin@example.com",
    "x-consumer-id": "test-admin-id",
    "x-authenticated-groups": "admin",
}


# ---------------------------------------------------------------------------
# App factories
# ---------------------------------------------------------------------------


def make_test_app() -> FastAPI:
    """Build a fully-wired FastAPI app suitable for integration tests.

    Uses a no-op lifespan so no MongoDB connection is required.  The
    verify_gateway dependency is NOT added at the app level here — tests that
    need gateway enforcement should use make_gateway_app() instead.
    """

    @asynccontextmanager
    async def _noop_lifespan(app: FastAPI):
        app.state.db = MagicMock()
        app.state.s3 = MagicMock()
        yield

    app = FastAPI(title="mpcontribs-test", lifespan=_noop_lifespan)
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)

    from mpcontribs_api.api.v1.router import router as v1_router

    app.include_router(v1_router, prefix="/api/v1")
    return app


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def test_app() -> FastAPI:
    return make_test_app()


@pytest.fixture
def client(test_app: FastAPI):
    """Function-scoped client; dependency overrides are cleared after each test."""
    with TestClient(test_app, raise_server_exceptions=False) as c:
        yield c
    test_app.dependency_overrides.clear()


@pytest.fixture
def gateway_client(gateway_app: FastAPI):
    with TestClient(gateway_app, raise_server_exceptions=False) as c:
        yield c
    gateway_app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Mock repository factories
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_project_repo() -> AsyncMock:
    """Fully async mock of MongoDbProjectRepository."""
    return AsyncMock()


@pytest.fixture
def mock_contribution_repo() -> AsyncMock:
    """Fully async mock of MongoDbContributionRepository."""
    return AsyncMock()


@pytest.fixture
def mock_structure_repo() -> AsyncMock:
    """Fully async mock of MongoDbStructureRepository."""
    return AsyncMock()


@pytest.fixture
def mock_table_repo() -> AsyncMock:
    """Fully async mock of MongoDbTableRepository."""
    return AsyncMock()


@pytest.fixture
def mock_attachment_repo() -> AsyncMock:
    """Fully async mock of MongoDbAttachmentRepository."""
    return AsyncMock()


@pytest.fixture
def mock_contribution_service() -> AsyncMock:
    """Fully async mock of ContributionService."""
    return AsyncMock()
