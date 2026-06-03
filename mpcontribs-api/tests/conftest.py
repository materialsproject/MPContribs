"""Shared pytest configuration and fixtures.

Environment variables for Settings are set at module level (before any source
imports) so that auth.py and config.py can load successfully without a real
.env file.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

# Must be set before any source import that calls get_settings().
os.environ.setdefault("MPCONTRIBS_ENVIRONMENT", "dev")
os.environ.setdefault("MPCONTRIBS_MONGO__URI", "mongodb://localhost:27017")
os.environ.setdefault("MPCONTRIBS_MONGO__DB_NAME", "testdb")
os.environ.setdefault("MPCONTRIBS_KONG__GATEWAY_SECRET", "test-gateway-secret")
os.environ.setdefault("MPCONTRIBS_REDIS__ADDRESS", "redis://localhost:6379")
os.environ.setdefault("MPCONTRIBS_REDIS__URL", "redis://localhost:6379")
os.environ.setdefault("MPCONTRIBS_MAIL_DEFAULT_SENDER", "test@example.com")
os.environ.setdefault("MPCONTRIBS_VERSION", "0.0.0-test")


@pytest.fixture(autouse=True, scope="session")
def _mock_beanie_collection():
    """Prevent CollectionWasNotInitialized for unit tests.

    Beanie Documents call get_pymongo_collection() in __init__ to assert the
    collection has been set up via init_beanie(). Unit tests don't need a real
    DB, so we stub that check out for the entire session.
    """
    import beanie

    with patch.object(beanie.Document, "get_pymongo_collection", return_value=MagicMock()):
        yield
