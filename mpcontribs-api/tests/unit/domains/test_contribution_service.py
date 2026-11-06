from unittest.mock import AsyncMock

import pytest

from mpcontribs_api.domains.contributions.service import ContributionService
from mpcontribs_api.exceptions import ValidationError

pytestmark = pytest.mark.asyncio


def _make_service() -> tuple[ContributionService, AsyncMock]:
    """Build a ContributionService over a mocked repository.

    Contributions are read-only on this server, so the service only depends on the contributions
    repository; the tests here cover the one piece of service-side logic (formula -> search terms).
    """
    contrib_repo = AsyncMock()
    svc = ContributionService(contributions=contrib_repo)
    return svc, contrib_repo


class TestSearch:
    """The service turns a query formula into the element-count permutations the repo matches on."""

    async def test_empty_query_is_rejected_before_any_db_work(self):
        svc, contrib_repo = _make_service()
        with pytest.raises(ValidationError, match="empty"):
            await svc.search("")
        contrib_repo.search.assert_not_called()

    async def test_invalid_formula_is_a_validation_error(self):
        svc, contrib_repo = _make_service()
        with pytest.raises(ValidationError, match="invalid formula"):
            await svc.search("not-a-formula!!")
        contrib_repo.search.assert_not_called()

    async def test_multi_element_formula_yields_every_ordering(self):
        svc, contrib_repo = _make_service()
        contrib_repo.search.return_value = []
        await svc.search("Fe2O3", limit=7)
        terms, limit = contrib_repo.search.await_args.args
        assert set(terms) == {"Fe2O3", "O3Fe2"}  # both permutations of the reduced element-counts
        assert limit == 7

    async def test_single_element_keeps_its_integer_count(self):
        svc, contrib_repo = _make_service()
        contrib_repo.search.return_value = []
        await svc.search("O2")
        terms, limit = contrib_repo.search.await_args.args
        assert terms == ["O2"]
        assert limit == 10  # default

    async def test_single_element_unit_count_drops_the_one(self):
        svc, contrib_repo = _make_service()
        contrib_repo.search.return_value = []
        await svc.search("Fe")
        terms, _ = contrib_repo.search.await_args.args
        assert terms == ["Fe"]

    async def test_repository_failure_propagates(self):
        svc, contrib_repo = _make_service()
        contrib_repo.search.side_effect = RuntimeError("atlas down")
        # Infra failures are not wrapped: they propagate to the global handler (a 500), rather than
        # being masked as a misleading "try a different formula" 4xx.
        with pytest.raises(RuntimeError, match="atlas down"):
            await svc.search("Fe2O3")
