import pytest

from mpcontribs_api.authz import (
    ADMIN_ROLE,
    INITIATIVE_PATH,
    PERSSON_ROLE,
    PROJECT_GROUP_PATH,
    PROJECT_PATH,
    ROOT_PATH,
    User,
    UserGroup,
    parse_grant,
)
from mpcontribs_api.exceptions import PermissionError

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
        grant = UserGroup.parse("mpcontribs:projects/mp-a=editor")
        assert grant is not None
        assert grant.path == ("mpcontribs", "projects", "mp-a")
        assert grant.role == "editor"

    def test_arn_arbitrary_depth(self):
        grant = UserGroup.parse("mpcontribs:projects/name/something/some_name=owner")
        assert grant is not None
        assert grant.path == ("mpcontribs", "projects", "name", "something", "some_name")
        assert grant.role == "owner"

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "   ",
            "mpcontribs:projects/mp-a=",  # empty role
            "mpcontribs:/mp-a=owner",  # empty segment
            "initiatives/solar",  # no '=' -> rejected
            "project-groups/deadbeef",  # no '=' -> rejected
        ],
    )
    def test_malformed_is_dropped(self, raw: str):
        assert UserGroup.parse(raw) is None

    def test_core_parse_rejects_legacy_forms(self):
        # The domain-neutral grammar (UserGroup.parse) understands ARN tokens only; the `=`-less
        # legacy forms are a server concern handled by ``parse_grant``, not the core.
        assert UserGroup.parse("mp-team") is None
        assert UserGroup.parse(ADMIN_ROLE) is None
        assert UserGroup.parse(PERSSON_ROLE) is None

    def test_legacy_bare_id_becomes_project_owner(self):
        grant = parse_grant("mp-team")
        assert grant is not None
        assert grant.path == ("mpcontribs", "projects", "mp-team")
        assert grant.role == "owner"

    def test_legacy_admin_sentinel(self):
        grant = parse_grant(ADMIN_ROLE)
        assert grant is not None
        assert grant.path == ("mpcontribs",)
        assert grant.role == ADMIN_ROLE

    def test_legacy_persson_sentinel(self):
        grant = parse_grant(PERSSON_ROLE)
        assert grant is not None
        assert grant.role == PERSSON_ROLE

    def test_str_round_trips_through_parse(self):
        grant = UserGroup.parse("mpcontribs:projects/mp-a=viewer")
        assert grant is not None
        assert str(grant) == "mpcontribs:projects/mp-a=viewer"
        assert UserGroup.parse(str(grant)) == grant

    def test_equals_in_name_is_rejected(self):
        # '=' is banned from names, so a stray '=' before the role suffix fails closed rather than
        # being swallowed into a segment (the role suffix stays unambiguous).
        assert UserGroup.parse("mpcontribs:projects/a=b=owner") is None


class TestUserIsAdmin:
    def test_no_groups_not_admin(self):
        assert User(username=ALICE).is_admin(*ROOT_PATH) is False

    def test_admin_arn_is_admin(self):
        assert User(username=ALICE, groups=["mpcontribs=admin"]).is_admin(*ROOT_PATH) is True

    def test_legacy_admin_sentinel_is_admin(self):
        assert User(username=ALICE, groups=[ADMIN_ROLE]).is_admin(*ROOT_PATH) is True

    def test_project_role_is_not_admin(self):
        assert User(username=ALICE, groups=["mpcontribs:projects/mp-a=owner"]).is_admin(*ROOT_PATH) is False

    def test_admin_among_many_is_admin(self):
        user = User(username=ALICE, groups=["mpcontribs:projects/mp-a=owner", "mpcontribs=admin"])
        assert user.is_admin(*ROOT_PATH) is True

    def test_anonymous_admin_grant_is_stripped(self):
        # A reserved grant on an anonymous caller (no username) must never confer admin.
        user = User(groups=["mpcontribs=admin"])
        assert user.is_anonymous is True
        assert user.is_admin(*ROOT_PATH) is False
        assert user.groups == ()

    def test_anonymous_persson_grant_is_stripped(self):
        user = User(groups=[PERSSON_ROLE])
        assert user.groups == ()


class TestTrieLookups:
    def test_role_for_exact_path(self):
        user = User(username=ALICE, groups=["mpcontribs:projects/mp-a=editor"])
        assert user.role_for("mpcontribs", "projects", "mp-a") == "editor"
        assert user.role_for("mpcontribs", "projects", "mp-b") is None

    def test_role_for_deep_path(self):
        user = User(username=ALICE, groups=["mpcontribs:projects/name/sub/leaf=owner"])
        assert user.role_for("mpcontribs", "projects", "name", "sub", "leaf") == "owner"
        # An intermediate node carries no role of its own.
        assert user.role_for("mpcontribs", "projects", "name") is None

    def test_has_grant_prefix(self):
        user = User(username=ALICE, groups=["mpcontribs:projects/name/sub/leaf=owner"])
        assert user.has_grant("mpcontribs", "projects", "name") is True
        assert user.has_grant("mpcontribs", "projects", "other") is False


class TestResourceMappings:
    def test_grants_in_project_maps_id_to_role(self):
        user = User(
            username=ALICE,
            groups=["mpcontribs:projects/mp-a=owner", "mpcontribs:projects/mp-b=viewer"],
        )
        assert user.grants_in(*PROJECT_PATH) == {"mp-a": "owner", "mp-b": "viewer"}

    def test_grants_in_initiative_and_project_group_scopes(self):
        user = User(
            username=ALICE,
            groups=[
                "mpcontribs:initiatives/solar=editor",
                "mpcontribs:project-groups/deadbeef=viewer",
            ],
        )
        assert user.grants_in(*INITIATIVE_PATH) == {"solar": "editor"}
        assert user.grants_in(*PROJECT_GROUP_PATH) == {"deadbeef": "viewer"}

    def test_deeper_grant_not_surfaced_as_resource(self):
        # A grant strictly beneath a project id is stored but not a direct project grant yet.
        user = User(username=ALICE, groups=["mpcontribs:projects/mp-a/sub=owner"])
        assert user.grants_in(*PROJECT_PATH) == {}
        assert user.has_grant("mpcontribs", "projects", "mp-a") is True


class TestReadWriteRoles:
    def test_any_role_is_present_for_read(self):
        # Read is presence-based: every granted role shows up in grants_in regardless of rank.
        user = User(
            username=ALICE,
            groups=["mpcontribs:projects/mp-a=viewer", "mpcontribs:projects/mp-b=editor"],
        )
        assert set(user.grants_in(*PROJECT_PATH)) == {"mp-a", "mp-b"}

    def test_writable_excludes_viewer(self):
        user = User(
            username=ALICE,
            groups=[
                "mpcontribs:projects/mp-a=viewer",
                "mpcontribs:projects/mp-b=editor",
                "mpcontribs:projects/mp-c=owner",
            ],
        )
        assert user.writable(*PROJECT_PATH) == frozenset({"mp-b", "mp-c"})

    def test_can_write_owner_and_editor_only(self):
        user = User(
            username=ALICE,
            groups=["mpcontribs:projects/mp-a=viewer", "mpcontribs:projects/mp-b=editor"],
        )
        assert user.can_write(*PROJECT_PATH, "mp-a") is False
        assert user.can_write(*PROJECT_PATH, "mp-b") is True

    def test_admin_can_write_any_project(self):
        assert User(username=ALICE, groups=["mpcontribs=admin"]).can_write(*PROJECT_PATH, "anything") is True

    def test_anonymous_has_no_writable(self):
        user = User()
        assert user.writable(*PROJECT_PATH) == frozenset()


class TestCanManage:
    def test_owner_can_manage(self):
        user = User(username=ALICE, groups=["mpcontribs:initiatives/solar=owner"])
        assert user.can_manage(*INITIATIVE_PATH, "solar") is True

    def test_editor_and_viewer_cannot_manage(self):
        editor = User(username=ALICE, groups=["mpcontribs:initiatives/solar=editor"])
        viewer = User(username=ALICE, groups=["mpcontribs:initiatives/solar=viewer"])
        assert editor.can_manage(*INITIATIVE_PATH, "solar") is False
        assert viewer.can_manage(*INITIATIVE_PATH, "solar") is False

    def test_admin_can_manage_anything(self):
        assert User(username=ALICE, groups=["mpcontribs=admin"]).can_manage(*INITIATIVE_PATH, "solar") is True

    def test_anonymous_cannot_manage(self):
        assert User().can_manage(*INITIATIVE_PATH, "solar") is False

    def test_doc_owner_can_manage_without_role(self):
        # The document's own owner manages it even with no ARN role grant.
        user = User(username=ALICE, groups=[])
        assert user.can_manage(*INITIATIVE_PATH, "solar", doc_owner=ALICE) is True
        assert user.can_manage(*INITIATIVE_PATH, "solar", doc_owner="someone-else") is False


class TestRequireGates:
    def test_require_write_passes_for_editor(self):
        user = User(username=ALICE, groups=["mpcontribs:projects/mp-a=editor"])
        user.require_write(*PROJECT_PATH, "mp-a")  # does not raise

    def test_require_write_raises_for_viewer(self):
        user = User(username=ALICE, groups=["mpcontribs:projects/mp-a=viewer"])
        with pytest.raises(PermissionError):
            user.require_write(*PROJECT_PATH, "mp-a")

    def test_require_write_denies_none_project(self):
        user = User(username=ALICE, groups=["mpcontribs=admin"])
        with pytest.raises(PermissionError):
            user.require_write(*PROJECT_PATH, None)

    def test_require_manage_passes_for_owner_role(self):
        user = User(username=ALICE, groups=["mpcontribs:initiatives/solar=owner"])
        user.require_manage(*INITIATIVE_PATH, "solar")  # does not raise

    def test_require_manage_passes_for_doc_owner(self):
        user = User(username=ALICE, groups=[])
        user.require_manage(*INITIATIVE_PATH, "solar", doc_owner=ALICE)  # does not raise

    def test_require_manage_raises_for_editor(self):
        user = User(username=ALICE, groups=["mpcontribs:initiatives/solar=editor"])
        with pytest.raises(PermissionError):
            user.require_manage(*INITIATIVE_PATH, "solar")


class TestCrossDomainPaths:
    """"Domain" is just path[0]: a grant under one root is invisible when a different root is asked.

    Two servers share the same users; a grant in another server's domain is carried on the trie but is
    invisible to this server's ``mpcontribs``-rooted paths unless that other root is named explicitly.
    """

    def test_grant_under_other_root_hidden(self):
        user = User(username=ALICE, groups=["core:projects/x=editor"])
        assert user.grants_in(*PROJECT_PATH) == {}
        assert user.grants_in("core", "projects") == {"x": "editor"}

    def test_can_write_respects_root(self):
        user = User(username=ALICE, groups=["core:projects/x=editor"])
        assert user.can_write(*PROJECT_PATH, "x") is False
        assert user.can_write("core", "projects", "x") is True

    def test_writable_respects_root(self):
        user = User(username=ALICE, groups=["core:projects/x=owner", "mpcontribs:projects/y=owner"])
        assert user.writable(*PROJECT_PATH) == frozenset({"y"})
        assert user.writable("core", "projects") == frozenset({"x"})

    def test_is_admin_respects_root(self):
        user = User(username=ALICE, groups=["core=admin"])
        # Admin under the "core" root is not admin under this server's mpcontribs root.
        assert user.is_admin(*ROOT_PATH) is False
        assert user.is_admin("core") is True

    def test_can_manage_respects_root(self):
        user = User(username=ALICE, groups=["core:initiatives/solar=owner"])
        assert user.can_manage(*INITIATIVE_PATH, "solar") is False
        assert user.can_manage("core", "initiatives", "solar") is True


class TestUserImmutability:
    def test_user_is_frozen(self):
        user = User(username=ALICE)
        with pytest.raises(Exception):
            user.username = "google:bob@example.com"  # type: ignore[misc]

    def test_user_is_hashable(self):
        user = User(username=ALICE, groups=["mpcontribs:projects/mp-a=owner"])
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
            groups=["mpcontribs:projects/mp-team=editor"],
        )
        assert user.consumer_id == "kong-consumer-123"
        assert user.username == ALICE
        assert user.can_write(*PROJECT_PATH, "mp-team") is True
        assert user.is_admin(*ROOT_PATH) is False
        assert user.is_anonymous is False

    def test_accepts_prebuilt_usergroup(self):
        grant = UserGroup(path=("mpcontribs", "projects", "mp-a"), role="owner")
        user = User(username=ALICE, groups=[grant])
        assert user.can_write(*PROJECT_PATH, "mp-a") is True
