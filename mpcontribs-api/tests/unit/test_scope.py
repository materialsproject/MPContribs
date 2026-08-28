"""Unit tests for the composable read-visibility scope (``mpcontribs_api.scope``).

Pure and DB-free. Two layers:
- each clause's ``to_query`` in isolation (including the ``None`` "inapplicable" cases and
  ``RoleIn`` coercion / invalid-drop);
- ``Scope.query`` composition (admin bypass, empty scope, ``$or`` element order);
- the per-repository ``read_scope`` declarations still produce the exact Mongo fragments the
  collections relied on (the integration ``db`` visibility suites remain the end-to-end guard).
"""

from beanie import PydanticObjectId

from mpcontribs_api.authz import PROJECT_GROUP_PATH, PROJECT_PATH, User
from mpcontribs_api.authz_core import Role
from mpcontribs_api.domains.contributions.repository import MongoDbContributionRepository
from mpcontribs_api.domains.initiatives.repository import MongoDbInitiativeRepository
from mpcontribs_api.domains.project_groups.repository import MongoDbProjectGroupRepository
from mpcontribs_api.domains.projects.repository import MongoDbProjectRepository
from mpcontribs_api.scope import Granted, Owned, Public, Scope

ADMIN = User(username="google:admin@example.com", groups=["mpcontribs=admin"])
ANON = User()
ALICE = User(username="google:alice@example.com", groups=[])


def _clauses(scope: dict) -> list[dict]:
    """The ``$or`` clauses of a non-empty scope."""
    return scope["$or"]


# ---------------------------------------------------------------------------
# Clauses in isolation
# ---------------------------------------------------------------------------


class TestPublicClause:
    def test_unapproved_public_only(self):
        assert Public().to_query(ANON) == {"is_public": True}

    def test_approved_adds_is_approved(self):
        assert Public(approved=True).to_query(ANON) == {"is_public": True, "is_approved": True}

    def test_applies_to_everyone(self):
        # Public is the baseline clause: it never returns None, even for anonymous callers.
        assert Public().to_query(ANON) is not None
        assert Public().to_query(ALICE) is not None


class TestOwnedClause:
    def test_authenticated_gets_owner_clause(self):
        assert Owned().to_query(ALICE) == {"owner": "google:alice@example.com"}

    def test_custom_owner_field(self):
        assert Owned("created_by").to_query(ALICE) == {"created_by": "google:alice@example.com"}

    def test_anonymous_is_inapplicable(self):
        # {owner: None} would wrongly match owner-less documents, so the clause drops out.
        assert Owned().to_query(ANON) is None


class TestGrantedClause:
    def test_membership_test_sorted(self):
        user = User(username="u@x.com", groups=["mpcontribs:projects/mp-b=owner", "mpcontribs:projects/mp-a=viewer"])
        assert Granted("_id", PROJECT_PATH).to_query(user) == {"_id": {"$in": ["mp-a", "mp-b"]}}

    def test_no_roles_is_inapplicable(self):
        user = User(username="u@x.com", groups=[])
        assert Granted("_id", PROJECT_PATH).to_query(user) is None

    def test_min_role_filters_below_threshold(self):
        # Default min_role is viewer (presence); raising it drops lower roles from visibility.
        user = User(username="u@x.com", groups=["mpcontribs:projects/mp-a=viewer", "mpcontribs:projects/mp-b=editor"])
        assert Granted("_id", PROJECT_PATH).to_query(user) == {"_id": {"$in": ["mp-a", "mp-b"]}}
        assert Granted("_id", PROJECT_PATH, min_role=Role.editor).to_query(user) == {"_id": {"$in": ["mp-b"]}}
        assert Granted("_id", PROJECT_PATH, min_role=Role.owner).to_query(user) is None

    def test_coerce_maps_each_value(self):
        oid = "a" * 24
        user = User(username="u@x.com", groups=[f"mpcontribs:project-groups/{oid}=viewer"])
        clause = Granted("_id", PROJECT_GROUP_PATH, coerce=PydanticObjectId)
        assert clause.to_query(user) == {"_id": {"$in": [PydanticObjectId(oid)]}}

    def test_coerce_drops_invalid_values(self):
        oid = "a" * 24
        user = User(
            username="u@x.com",
            groups=[f"mpcontribs:project-groups/{oid}=viewer", "mpcontribs:project-groups/not-an-oid=viewer"],
        )
        clause = Granted("_id", PROJECT_GROUP_PATH, coerce=PydanticObjectId)
        # The malformed hex string is fail-closed dropped; only the valid ObjectId survives.
        assert clause.to_query(user) == {"_id": {"$in": [PydanticObjectId(oid)]}}

    def test_coerce_all_invalid_is_inapplicable(self):
        user = User(username="u@x.com", groups=["mpcontribs:project-groups/nope=viewer"])
        clause = Granted("_id", PROJECT_GROUP_PATH, coerce=PydanticObjectId)
        assert clause.to_query(user) is None

    def test_path_selects_grant_source(self):
        # A clause reads grants under its own path prefix; a different root's grants are invisible to it.
        user = User(
            username="u@x.com",
            groups=["mpcontribs:projects/mp-a=owner", "core:projects/mp-b=owner"],
        )
        assert Granted("_id", PROJECT_PATH).to_query(user) == {"_id": {"$in": ["mp-a"]}}
        assert Granted("_id", ("core", "projects")).to_query(user) == {"_id": {"$in": ["mp-b"]}}


# ---------------------------------------------------------------------------
# Scope composition
# ---------------------------------------------------------------------------


class TestScopeQuery:
    scope = Scope(Public(approved=True), Owned(), Granted("_id", PROJECT_PATH))

    def test_admin_bypasses_scope(self):
        assert self.scope.query(ADMIN) == {}

    def test_empty_scope_matches_all(self):
        # No clauses (unscoped collection) → no filter, for any caller.
        assert Scope().query(ANON) == {}
        assert Scope().query(ALICE) == {}

    def test_anonymous_gets_only_applicable_clauses(self):
        # Public applies; Owned and (no-role) RoleIn drop out.
        assert self.scope.query(ANON) == {"$or": [{"is_public": True, "is_approved": True}]}

    def test_clause_order_preserved(self):
        user = User(username="alice@x.com", groups=["mpcontribs:projects/mp-a=owner"])
        assert _clauses(self.scope.query(user)) == [
            {"is_public": True, "is_approved": True},
            {"owner": "alice@x.com"},
            {"_id": {"$in": ["mp-a"]}},
        ]


# ---------------------------------------------------------------------------
# Per-repository declarations reproduce the expected fragments
# ---------------------------------------------------------------------------


class TestProjectScope:
    scope = MongoDbProjectRepository.read_scope

    def test_admin_unfiltered(self):
        assert self.scope.query(ADMIN) == {}

    def test_public_approved_owner_and_project_ids(self):
        user = User(username="alice@x.com", groups=["mpcontribs:projects/mp-a=owner", "mpcontribs:projects/mp-b=viewer"])
        clauses = _clauses(self.scope.query(user))
        assert {"is_public": True, "is_approved": True} in clauses
        assert {"owner": "alice@x.com"} in clauses
        assert {"_id": {"$in": ["mp-a", "mp-b"]}} in clauses

    def test_other_scopes_excluded_from_id_clause(self):
        # Only project-scoped grants may key the _id clause; other scopes/admin must not leak in.
        user = User(
            username="alice@x.com",
            groups=[
                "mpcontribs:projects/mp-a=owner",
                "mpcontribs:initiatives/foo=owner",
                "mpcontribs:project-groups/deadbeef=owner",
            ],
        )
        role_clause = next(c for c in _clauses(self.scope.query(user)) if "_id" in c)
        assert role_clause == {"_id": {"$in": ["mp-a"]}}


class TestInitiativeScope:
    scope = MongoDbInitiativeRepository.read_scope

    def test_admin_unfiltered(self):
        assert self.scope.query(ADMIN) == {}

    def test_public_approved_owner_and_slug_roles(self):
        user = User(username="alice@x.com", groups=["mpcontribs:initiatives/solar=viewer"])
        clauses = _clauses(self.scope.query(user))
        assert {"is_public": True, "is_approved": True} in clauses
        assert {"owner": "alice@x.com"} in clauses
        assert {"slug": {"$in": ["solar"]}} in clauses


class TestProjectGroupScope:
    scope = MongoDbProjectGroupRepository.read_scope

    def test_admin_unfiltered(self):
        assert self.scope.query(ADMIN) == {}

    def test_public_clause_has_no_approval(self):
        clauses = _clauses(self.scope.query(ANON))
        assert {"is_public": True} in clauses
        assert all("is_approved" not in c for c in clauses)

    def test_valid_group_roles_become_objectids_invalid_dropped(self):
        oid = "a" * 24
        user = User(
            username="alice@x.com",
            groups=[f"mpcontribs:project-groups/{oid}=viewer", "mpcontribs:project-groups/not-an-oid=viewer"],
        )
        role_clause = next(c for c in _clauses(self.scope.query(user)) if "_id" in c)
        assert role_clause == {"_id": {"$in": [PydanticObjectId(oid)]}}


class TestContributionScope:
    scope = MongoDbContributionRepository.read_scope

    def test_admin_unfiltered(self):
        assert self.scope.query(ADMIN) == {}

    def test_no_owner_clause_and_public_unapproved(self):
        user = User(username="alice@x.com", groups=["mpcontribs:projects/mp-a=owner"])
        clauses = _clauses(self.scope.query(user))
        assert {"is_public": True} in clauses
        assert all("owner" not in c for c in clauses)
        assert {"project": {"$in": ["mp-a"]}} in clauses

    def test_viewer_can_read_contributions(self):
        # Read visibility is presence-based: a project viewer sees the project's contributions.
        user = User(username="alice@x.com", groups=["mpcontribs:projects/mp-a=viewer"])
        clauses = _clauses(self.scope.query(user))
        assert {"project": {"$in": ["mp-a"]}} in clauses

    def test_anonymous_only_public(self):
        assert _clauses(self.scope.query(ANON)) == [{"is_public": True}]
