from unittest.mock import MagicMock

import pytest

from mpcontribs_api.authz import PROJECT_PATH, User
from mpcontribs_api.dependencies import _split, get_user, require_user
from mpcontribs_api.exceptions import AuthenticationError

# ---------------------------------------------------------------------------
# _split
# ---------------------------------------------------------------------------


class TestSplit:
    def test_none_returns_empty_set(self):
        assert _split(None) == set()

    def test_empty_string_returns_empty_set(self):
        assert _split("") == set()

    def test_whitespace_only_returns_empty_set(self):
        assert _split("   ") == set()

    def test_single_value(self):
        assert _split("editors") == {"editors"}

    def test_multiple_values(self):
        assert _split("editors,viewers,admins") == {"editors", "viewers", "admins"}

    def test_strips_whitespace(self):
        assert _split(" editors , viewers ") == {"editors", "viewers"}

    def test_skips_empty_parts(self):
        assert _split("editors,,viewers") == {"editors", "viewers"}

    def test_single_space_comma_separated(self):
        assert _split("a, b, c") == {"a", "b", "c"}


# ---------------------------------------------------------------------------
# get_user — builds User from request headers
# ---------------------------------------------------------------------------


def _make_request(**headers: str) -> MagicMock:
    """Build a mock Request whose .headers dict returns the given values."""
    request = MagicMock()
    request.headers = headers
    return request


class TestGetUser:
    def test_no_headers_returns_anonymous(self):
        request = _make_request()
        user = get_user(request)
        assert user.is_anonymous is True

    def test_explicit_anon_header_returns_anonymous(self):
        request = _make_request(**{"x-anonymous-consumer": "true", "x-consumer-username": "alice"})
        user = get_user(request)
        assert user.is_anonymous is True

    def test_explicit_anon_case_insensitive(self):
        request = _make_request(**{"x-anonymous-consumer": "True", "x-consumer-username": "alice"})
        user = get_user(request)
        assert user.is_anonymous is True

    def test_authenticated_user(self):
        request = _make_request(
            **{
                "x-consumer-username": "google:alice@example.com",
                "x-consumer-id": "kong-123",
                "x-authenticated-groups": "editors",
                "x-consumer-groups": "mp-team",
            }
        )
        user = get_user(request)
        assert user.is_anonymous is False
        assert user.username == "google:alice@example.com"
        assert user.consumer_id == "kong-123"
        # Bare legacy tokens from either header become project grants (default owner role).
        assert user.grants_in(*PROJECT_PATH) == {"editors": "owner", "mp-team": "owner"}

    def test_full_arn_grant_from_header(self):
        # A full new-format ARN string (not a bare legacy token) arriving via Kong headers parses
        # end-to-end through the comma-split and grant parser, keeping its own role.
        request = _make_request(
            **{
                "x-consumer-username": "google:alice@example.com",
                "x-authenticated-groups": "mpcontribs:projects/mp-a=editor",
            }
        )
        user = get_user(request)
        assert user.grants_in(*PROJECT_PATH) == {"mp-a": "editor"}
        assert user.can_write(*PROJECT_PATH, "mp-a") is True

    def test_authenticated_user_no_groups(self):
        request = _make_request(**{"x-consumer-username": "google:alice@example.com"})
        user = get_user(request)
        assert user.is_anonymous is False
        assert user.groups == ()

    def test_groups_merged_from_both_headers(self):
        request = _make_request(
            **{
                "x-consumer-username": "google:alice@example.com",
                "x-authenticated-groups": "a,b",
                "x-consumer-groups": "c,d",
            }
        )
        user = get_user(request)
        assert user.grants_in(*PROJECT_PATH) == {"a": "owner", "b": "owner", "c": "owner", "d": "owner"}

    def test_missing_username_returns_anonymous(self):
        request = _make_request(**{"x-consumer-id": "kong-123"})
        user = get_user(request)
        assert user.is_anonymous is True


# ---------------------------------------------------------------------------
# require_user
# ---------------------------------------------------------------------------


class TestRequireUser:
    def test_authenticated_user_passes_through(self):
        authed = User(username="google:alice@example.com", groups=[])
        result = require_user(authed)
        assert result is authed

    def test_anonymous_raises_authentication_error(self):
        anon = User()
        with pytest.raises(AuthenticationError):
            require_user(anon)
