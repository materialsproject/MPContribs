"""Tests for the GET /limits contract endpoint."""

from unittest.mock import AsyncMock

import pytest

from mpcontribs_api.config import get_settings
from mpcontribs_api.domains.consumers.dependencies import get_consumer_service


class TestLimitsEndpoint:
    @pytest.fixture(autouse=True)
    def _stub_consumer_service(self, test_app):
        # GET /limits resolves the caller's effective per-consumer max_components via ConsumerService,
        # which needs Mongo; these route tests run without a DB, so stub it to return global defaults.
        service = AsyncMock()
        service.effective_limits.return_value = get_settings().consumer
        test_app.dependency_overrides[get_consumer_service] = lambda: service
        yield
        test_app.dependency_overrides.pop(get_consumer_service, None)

    def test_limits_reports_configured_values(self, client):
        mongo = get_settings().mongo
        consumer = get_settings().consumer
        r = client.get("/api/v1/limits")
        assert r.status_code == 200
        assert r.json() == {
            "max_request_bytes": mongo.max_request_bytes,
            "bulk_write_limit": mongo.bulk_write_limit,
            "max_components": consumer.contribution.max_components,
            "component_insert_chunk_size": mongo.component_insert_chunk_size,
        }

    def test_limits_is_public(self, client):
        # No auth headers: still readable (public metadata).
        client.headers.clear()
        assert client.get("/api/v1/limits").status_code == 200
