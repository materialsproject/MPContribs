import pytest

from mpcontribs_api.authz import ADMIN_ROLE, PERSSON_ROLE, User, UserGroup

ALICE = "google:alice@example.com"


class TestUserIsAnonymous:
    def test_no_username_is_anonymous(self):
        assert User().is_anonymous is True

    def test_username_none_is_anonymous(self):
        assert User(username=None).is_anonymous is True

    def test_with_username_not_anonymous(self):
        assert User(username=ALICE).is_anonymous is False


class TestUserGroupParse:
    def test_arn_depth_one(self):
        grant = UserGroup.parse("mpcontribs=admin")
        assert grant is not None
        assert grant.path == ("mpcontribs",)
        assert grant.role == "admin"

    def test_arn_depth_three(self):
        grant = UserGroup.parse("mpcontribs:project:mp-a=editor")
        assert grant is not None
        assert grant.path == ("mpcontribs", "project", "mp-a")
        assert grant.role == "editor"

    def test_arn_arbitrary_depth(self):
        grant = UserGroup.parse("mpcontribs:project:name:something:some_name=owner")
        assert grant is not None
        assert grant.path == ("mpcontribs", "project", "name", "something", "some_name")
        assert grant.role == "owner"

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "   ",
            "mpcontribs:project:mp-a=",  # empty role
            "mpcontribs::mp-a=owner",  # empty segment
            "initiative:solar",  # prefixed legacy, no '=' -> no longer supported
            "project-group:deadbeef",  # prefixed legacy, no '=' -> no longer supported
        ],
    )
    def test_malformed_is_dropped(self, raw: str):
        assert UserGroup.parse(raw) is None

    def test_legacy_bare_id_becomes_project_owner(self):
        grant = UserGroup.parse("mp-team")
        assert grant is not None
        assert grant.path == ("mpcontribs", "project", "mp-team")
        assert grant.role == "owner"

    def test_legacy_admin_sentinel(self):
        grant = UserGroup.parse(ADMIN_ROLE)
        assert grant is not None
        assert grant.path == ("mpcontribs",)
        assert grant.role == ADMIN_ROLE

    def test_legacy_persson_sentinel(self):
        grant = UserGroup.parse(PERSSON_ROLE)
        assert grant is not None
        assert grant.role == PERSSON_ROLE

    def test_str_round_trips_through_parse(self):
        grant = UserGroup.parse("mpcontribs:project:mp-a=viewer")
        assert grant is not None
        assert str(grant) == "mpcontribs:project:mp-a=viewer"
        assert UserGroup.parse(str(grant)) == grant

    def test_role_value_with_equals_uses_last(self):
        # rsplit on the last '=' keeps a stray '=' inside a segment out of the role.
        grant = UserGroup.parse("mpcontribs:project:a=b=owner")
        assert grant is not None
        assert grant.path == ("mpcontribs", "project", "a=b")
        assert grant.role == "owner"


class TestUserIsAdmin:
    def test_no_groups_not_admin(self):
        assert User(username=ALICE).is_admin is False

    def test_admin_arn_is_admin(self):
        assert User(username=ALICE, groups=["mpcontribs=admin"]).is_admin is True

    def test_legacy_admin_sentinel_is_admin(self):
        assert User(username=ALICE, groups=[ADMIN_ROLE]).is_admin is True

    def test_project_role_is_not_admin(self):
        assert User(username=ALICE, groups=["mpcontribs:project:mp-a=owner"]).is_admin is False

    def test_admin_among_many_is_admin(self):
        user = User(username=ALICE, groups=["mpcontribs:project:mp-a=owner", "mpcontribs=admin"])
        assert user.is_admin is True

    def test_anonymous_admin_grant_is_stripped(self):
        # A reserved grant on an anonymous caller (no username) must never confer admin.
        user = User(groups=["mpcontribs=admin"])
        assert user.is_anonymous is True
        assert user.is_admin is False
        assert user.groups == ()

    def test_anonymous_persson_grant_is_stripped(self):
        user = User(groups=[PERSSON_ROLE])
        assert user.groups == ()


class TestTrieLookups:
    def test_role_for_exact_path(self):
        user = User(username=ALICE, groups=["mpcontribs:project:mp-a=editor"])
        assert user.role_for("mpcontribs", "project", "mp-a") == "editor"
        assert user.role_for("mpcontribs", "project", "mp-b") is None

    def test_role_for_deep_path(self):
        user = User(username=ALICE, groups=["mpcontribs:project:name:sub:leaf=owner"])
        assert user.role_for("mpcontribs", "project", "name", "sub", "leaf") == "owner"
        # An intermediate node carries no role of its own.
        assert user.role_for("mpcontribs", "project", "name") is None

    def test_has_grant_prefix(self):
        user = User(username=ALICE, groups=["mpcontribs:project:name:sub:leaf=owner"])
        assert user.has_grant("mpcontribs", "project", "name") is True
        assert user.has_grant("mpcontribs", "project", "other") is False


class TestResourceMappings:
    def test_project_groups_maps_id_to_role(self):
        user = User(
            username=ALICE,
            groups=["mpcontribs:project:mp-a=owner", "mpcontribs:project:mp-b=viewer"],
        )
        assert user.project_groups == {"mp-a": "owner", "mp-b": "viewer"}

    def test_initiative_and_project_group_scopes(self):
        user = User(
            username=ALICE,
            groups=[
                "mpcontribs:initiative:solar=editor",
                "mpcontribs:project-group:deadbeef=viewer",
            ],
        )
        assert user.initiative_groups == {"solar": "editor"}
        assert user.project_group_groups == {"deadbeef": "viewer"}

    def test_deeper_grant_not_surfaced_as_resource(self):
        # A grant strictly beneath a project id is stored but not a direct project grant yet.
        user = User(username=ALICE, groups=["mpcontribs:project:mp-a:sub=owner"])
        assert user.project_groups == {}
        assert user.has_grant("mpcontribs", "project", "mp-a") is True


class TestReadWriteRoles:
    def test_readable_includes_viewer(self):
        user = User(
            username=ALICE,
            groups=["mpcontribs:project:mp-a=viewer", "mpcontribs:project:mp-b=editor"],
        )
        assert user.readable_projects == frozenset({"mp-a", "mp-b"})

    def test_writable_excludes_viewer(self):
        user = User(
            username=ALICE,
            groups=[
                "mpcontribs:project:mp-a=viewer",
                "mpcontribs:project:mp-b=editor",
                "mpcontribs:project:mp-c=owner",
            ],
        )
        assert user.writable_projects == frozenset({"mp-b", "mp-c"})

    def test_can_write_owner_and_editor_only(self):
        user = User(
            username=ALICE,
            groups=["mpcontribs:project:mp-a=viewer", "mpcontribs:project:mp-b=editor"],
        )
        assert user.can_write("mp-a") is False
        assert user.can_write("mp-b") is True

    def test_admin_can_write_any_project(self):
        assert User(username=ALICE, groups=["mpcontribs=admin"]).can_write("anything") is True

    def test_anonymous_has_no_writable_or_readable(self):
        user = User()
        assert user.writable_projects == frozenset()
        assert user.readable_projects == frozenset()


class TestCanManage:
    def test_owner_can_manage(self):
        user = User(username=ALICE, groups=["mpcontribs:initiative:solar=owner"])
        assert user.can_manage("solar", "initiative") is True

    def test_editor_and_viewer_cannot_manage(self):
        editor = User(username=ALICE, groups=["mpcontribs:initiative:solar=editor"])
        viewer = User(username=ALICE, groups=["mpcontribs:initiative:solar=viewer"])
        assert editor.can_manage("solar", "initiative") is False
        assert viewer.can_manage("solar", "initiative") is False

    def test_admin_can_manage_anything(self):
        assert User(username=ALICE, groups=["mpcontribs=admin"]).can_manage("solar", "initiative") is True

    def test_anonymous_cannot_manage(self):
        assert User().can_manage("solar", "initiative") is False


class TestUserImmutability:
    def test_user_is_frozen(self):
        user = User(username=ALICE)
        with pytest.raises(Exception):
            user.username = "google:bob@example.com"  # type: ignore[misc]

    def test_user_is_hashable(self):
        user = User(username=ALICE, groups=["mpcontribs:project:mp-a=owner"])
        assert isinstance(hash(user), int)

    def test_groups_default_empty(self):
        assert User().groups == ()

    def test_consumer_id_default_none(self):
        assert User().consumer_id is None


class TestUserConstruction:
    def test_full_user(self):
        user = User(
            consumer_id="kong-consumer-123",
            username=ALICE,
            groups=["mpcontribs:project:mp-team=editor"],
        )
        assert user.consumer_id == "kong-consumer-123"
        assert user.username == ALICE
        assert user.can_write("mp-team") is True
        assert user.is_admin is False
        assert user.is_anonymous is False

    def test_accepts_prebuilt_usergroup(self):
        grant = UserGroup(path=("mpcontribs", "project", "mp-a"), role="owner")
        user = User(username=ALICE, groups=[grant])
        assert user.can_write("mp-a") is True
