"""Unit tests for the domain-agnostic authorization core (``mpcontribs_api.authz_core``).

This is the shared grant-validation contract both API servers rely on: pure ARN grammar, the role
hierarchy, and a :class:`User` whose accessors are **path-based** — they take a generic ``*path`` of
ARN segments and give the first segment ("the domain") no special meaning beyond being where an admin
grant sits. ``ADMIN_ROLE``/``PERSSON_ROLE`` are the globally reserved keywords bound as the core's
defaults; a local subclass shows those hooks can be re-bound.
"""

from typing import ClassVar

import pytest

from mpcontribs_api.authz_core import ADMIN_ROLE, PERSSON_ROLE, ReservedRole, Role, User, UserGroup
from mpcontribs_api.exceptions import PermissionError

ALICE = "google:alice@example.com"


class CoreUser(User):
    """Re-binds the core's admin hook to a *different* reserved role, proving the hook is overridable.

    The default admin role is ``ReservedRole.admin``; this subclass makes ``persson_group`` the role
    that confers admin instead (and the only role stripped from anonymous callers), so its ``=admin``
    grants are ordinary while its ``=persson_group`` grants are the elevated ones.
    """

    admin_role: ClassVar[ReservedRole | None] = ReservedRole.persson_group
    reserved_roles: ClassVar[frozenset[ReservedRole]] = frozenset({ReservedRole.persson_group})


class TestRole:
    def test_hierarchy_order(self):
        assert Role.viewer < Role.editor < Role.owner
        assert Role.owner >= Role.editor >= Role.viewer

    def test_parse_known_and_unknown(self):
        assert Role.parse("editor") is Role.editor
        assert Role.parse("root") is None  # reserved/unknown roles never rank
        assert Role.parse(None) is None


class TestUserGroupGrammar:
    def test_parses_arbitrary_depth(self):
        grant = UserGroup.parse("d:a/b/c=owner")
        assert grant is not None
        assert grant.path == ("d", "a", "b", "c")
        assert grant.role == "owner"
        assert grant.domain == "d"

    def test_rejects_equals_in_name(self):
        # '=' is banned from names, so a stray '=' before the role suffix fails closed rather than
        # being swallowed into a segment (the delimiter role suffix stays unambiguous).
        assert UserGroup.parse("d:proj/a=b=owner") is None

    def test_str_round_trips(self):
        grant = UserGroup.parse("d:proj/mp-a=viewer")
        assert grant is not None
        assert str(grant) == "d:proj/mp-a=viewer"
        assert UserGroup.parse(str(grant)) == grant

    def test_domain_root_grant_round_trips(self):
        grant = UserGroup.parse("d=admin")
        assert grant is not None
        assert grant.path == ("d",)
        assert str(grant) == "d=admin"

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "   ",
            "d:proj/mp-a=",  # empty role
            "d:/mp-a=owner",  # empty segment
            "mp-team",  # no '=': legacy form is a server concern, not the neutral grammar
            "root",  # bare sentinel: also '='-less, rejected by the core
            "d:proj/mp-a",  # no '='
        ],
    )
    def test_rejects_non_arn(self, raw: str):
        assert UserGroup.parse(raw) is None


class TestTrieLookups:
    def test_role_for_and_has_grant(self):
        user = CoreUser(username=ALICE, groups=["d:proj/name/sub=owner"])
        assert user.role_for("d", "proj", "name", "sub") == "owner"
        assert user.role_for("d", "proj", "name") is None  # intermediate node carries no role
        assert user.has_grant("d", "proj", "name") is True
        assert user.has_grant("d", "proj", "other") is False

    def test_grants_in_by_path(self):
        user = CoreUser(username=ALICE, groups=["d:proj/mp-a=owner", "d:proj/mp-b=viewer"])
        assert user.grants_in("d", "proj") == {"mp-a": "owner", "mp-b": "viewer"}
        assert user.grants_in("other", "proj") == {}


class TestPathBasedAccessors:
    def test_is_admin_is_per_path(self):
        user = CoreUser(username=ALICE, groups=["d=persson_group"])
        assert user.is_admin("d") is True
        assert user.is_admin("other") is False

    def test_bare_core_uses_global_admin_role(self):
        # The core binds ADMIN_ROLE ("admin") as the default admin role; another valid role is not admin.
        assert User(username=ALICE, groups=["d=admin"]).is_admin("d") is True
        assert User(username=ALICE, groups=["d=owner"]).is_admin("d") is False

    def test_writable_and_can_write(self):
        user = CoreUser(
            username=ALICE,
            groups=["d:proj/a=viewer", "d:proj/b=editor", "d:proj/c=owner"],
        )
        assert user.writable("d", "proj") == frozenset({"b", "c"})
        assert user.can_write("d", "proj", "a") is False
        assert user.can_write("d", "proj", "b") is True

    def test_admin_can_write_anything_under_its_root(self):
        user = CoreUser(username=ALICE, groups=["d=persson_group"])
        assert user.can_write("d", "proj", "anything") is True
        assert user.can_write("other", "proj", "anything") is False

    def test_can_write_denies_none_segment_even_for_admin(self):
        user = CoreUser(username=ALICE, groups=["d=persson_group"])
        assert user.can_write("d", "proj", None) is False

    def test_can_manage_owner_and_doc_owner(self):
        owner = CoreUser(username=ALICE, groups=["d:init/solar=owner"])
        assert owner.can_manage("d", "init", "solar") is True
        editor = CoreUser(username=ALICE, groups=["d:init/solar=editor"])
        assert editor.can_manage("d", "init", "solar") is False
        # The document's own owner manages it with no role grant at all.
        plain = CoreUser(username=ALICE, groups=[])
        assert plain.can_manage("d", "init", "solar", doc_owner=ALICE) is True
        assert plain.can_manage("d", "init", "solar", doc_owner="someone-else") is False

    def test_cross_domain_isolation(self):
        # "domain" is just path[0]: a grant under one root is invisible when a different root is asked.
        user = CoreUser(username=ALICE, groups=["core:proj/x=owner"])
        assert user.writable("mpcontribs", "proj") == frozenset()
        assert user.writable("core", "proj") == frozenset({"x"})
        assert user.can_write("mpcontribs", "proj", "x") is False
        assert user.can_write("core", "proj", "x") is True


class TestRequireGates:
    def test_require_write_raises_for_viewer(self):
        user = CoreUser(username=ALICE, groups=["d:proj/a=viewer"])
        with pytest.raises(PermissionError):
            user.require_write("d", "proj", "a")

    def test_require_write_denies_none_segment(self):
        user = CoreUser(username=ALICE, groups=["d=persson_group"])
        with pytest.raises(PermissionError):
            user.require_write("d", "proj", None)

    def test_require_manage_passes_for_owner(self):
        user = CoreUser(username=ALICE, groups=["d:init/solar=owner"])
        user.require_manage("d", "init", "solar")  # does not raise

    def test_require_manage_raises_for_editor(self):
        user = CoreUser(username=ALICE, groups=["d:init/solar=editor"])
        with pytest.raises(PermissionError):
            user.require_manage("d", "init", "solar")


class TestReservedRoleStripping:
    def test_anonymous_reserved_grant_stripped(self):
        # A reserved-role grant (CoreUser's admin sentinel) must never survive on an anonymous caller.
        user = CoreUser(groups=["d=persson_group"])
        assert user.is_anonymous is True
        assert user.groups == ()
        assert user.is_admin("d") is False

    def test_authenticated_reserved_grant_kept(self):
        user = CoreUser(username=ALICE, groups=["d=persson_group"])
        assert user.is_admin("d") is True

    def test_globally_reserved_roles_are_stripped_from_anonymous(self):
        # The core reserves ADMIN_ROLE/PERSSON_ROLE globally: neither survives on an anonymous caller.
        assert User(groups=[f"d={ADMIN_ROLE}"]).groups == ()
        assert User(groups=[f"d={PERSSON_ROLE}"]).groups == ()
        # A non-reserved role is kept even when anonymous.
        assert User(groups=["d:proj/x=owner"]).groups != ()
