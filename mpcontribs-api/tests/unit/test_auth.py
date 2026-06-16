import pytest

from mpcontribs_api.authz import ADMIN_GROUP, User


class TestUserIsAnonymous:
    def test_no_username_is_anonymous(self):
        user = User()
        assert user.is_anonymous is True

    def test_username_none_is_anonymous(self):
        user = User(username=None)
        assert user.is_anonymous is True

    def test_with_username_not_anonymous(self):
        user = User(username="google:alice@example.com")
        assert user.is_anonymous is False


class TestUserIsAdmin:
    def test_no_groups_not_admin(self):
        user = User(username="google:alice@example.com")
        assert user.is_admin is False

    def test_admin_group_is_admin(self):
        user = User(username="google:alice@example.com", groups=frozenset({ADMIN_GROUP}))
        assert user.is_admin is True

    def test_other_group_not_admin(self):
        user = User(username="google:alice@example.com", groups=frozenset({"editors"}))
        assert user.is_admin is False

    def test_admin_group_among_many_is_admin(self):
        user = User(username="google:alice@example.com", groups=frozenset({"editors", ADMIN_GROUP, "viewers"}))
        assert user.is_admin is True

    def test_anonymous_cannot_be_admin(self):
        # Even if groups include admin, anonymous user (no username) is still anonymous
        user = User(groups=frozenset({ADMIN_GROUP}))
        assert user.is_anonymous is True
        # But is_admin only checks groups, not username
        assert user.is_admin is False


class TestUserHasRole:
    def test_has_role_in_groups(self):
        user = User(username="google:alice@example.com", groups=frozenset({"editors", "viewers"}))
        assert user.has_role("editors") is True

    def test_has_role_not_in_groups(self):
        user = User(username="google:alice@example.com", groups=frozenset({"editors"}))
        assert user.has_role("viewers") is False

    def test_has_role_empty_groups(self):
        user = User(username="google:alice@example.com")
        assert user.has_role("editors") is False

    def test_has_role_case_sensitive(self):
        user = User(username="google:alice@example.com", groups=frozenset({"Editors"}))
        assert user.has_role("editors") is False
        assert user.has_role("Editors") is True


class TestUserImmutability:
    def test_user_is_frozen(self):
        user = User(username="google:alice@example.com")
        with pytest.raises(Exception):
            user.username = "google:bob@example.com"  # type: ignore[misc]

    def test_groups_default_empty_frozenset(self):
        user = User()
        assert user.groups == frozenset()

    def test_consumer_id_default_none(self):
        user = User()
        assert user.consumer_id is None


class TestUserConstruction:
    def test_full_user(self):
        user = User(
            consumer_id="kong-consumer-123",
            username="google:alice@example.com",
            groups=frozenset({"editors", "mp-team"}),
        )
        assert user.consumer_id == "kong-consumer-123"
        assert user.username == "google:alice@example.com"
        assert "editors" in user.groups
        assert "admin" not in user.groups
        assert user.is_admin is False
        assert user.is_anonymous is False
