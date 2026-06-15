from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True, scope="session")
def _mock_beanie_collection():
    import beanie

    with patch.object(beanie.Document, "get_pymongo_collection", return_value=MagicMock()):
        yield
