"""Unit-test-only fixtures.

The Beanie collection mock lives here (not the root conftest) so it is
applied only to unit tests and does not interfere with DB integration tests
that need real Beanie initialization.
"""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True, scope="session")
def _mock_beanie_collection():
    import beanie

    with patch.object(beanie.Document, "get_pymongo_collection", return_value=MagicMock()):
        yield
