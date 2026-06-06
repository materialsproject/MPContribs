from datetime import UTC, datetime

import pytest
from beanie import PydanticObjectId
from pydantic import ValidationError as PydanticValidationError

from mpcontribs_api.auth import User
from mpcontribs_api.domains.contributions.repository import MongoDbContributionRepository

from mpcontribs_api.domains.contributions.models import (
    Contribution,
    ContributionIn,
    ContributionOut,
    ContributionPatch,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_contribution_in(**overrides) -> ContributionIn:
    """Build a minimal valid ContributionIn for testing."""
    defaults: dict = {
        "_id": PydanticObjectId(),
        "project": "test-project",
        "identifier": "mp-1234",
        "formula": "Fe2O3",
        "data": {"band_gap": {"value": 2.1, "unit": "eV"}},
    }
    defaults.update(overrides)
    return ContributionIn(**defaults)


# ---------------------------------------------------------------------------
# ContributionBase field validation
# ---------------------------------------------------------------------------


class TestContributionBase:
    def test_required_fields_set_correctly(self):
        contrib = ContributionIn(
            **{
                "_id": PydanticObjectId(),
                "project": "mp-project",
                "identifier": "mp-001",
                "formula": "Fe2O3",
                "data": {},
            }
        )
        assert contrib.project == "mp-project"
        assert contrib.identifier == "mp-001"
        assert contrib.formula == "Fe2O3"
        assert contrib.data == {}

    def test_defaults(self):
        contrib = _make_contribution_in()
        assert contrib.needs_build is True
        assert contrib.structures is None
        assert contrib.tables is None
        assert contrib.attachments is None

    def test_last_modified_defaults_to_now(self):
        before = datetime.now(UTC)
        contrib = _make_contribution_in()
        after = datetime.now(UTC)
        assert before <= contrib.last_modified <= after

    def test_missing_project_raises(self):
        with pytest.raises(PydanticValidationError):
            ContributionIn(
                **{
                    "_id": PydanticObjectId(),
                    "identifier": "mp-001",
                    "formula": "Fe",
                    "data": {},
                }
            )

    def test_missing_formula_raises(self):
        with pytest.raises(PydanticValidationError):
            ContributionIn(
                **{
                    "_id": PydanticObjectId(),
                    "project": "proj",
                    "identifier": "mp-001",
                    "data": {},
                }
            )

    def test_data_can_be_empty_dict(self):
        contrib = _make_contribution_in(data={})
        assert contrib.data == {}

    def test_data_accepts_nested_structure(self):
        nested = {"band_gap": {"value": 1.5, "unit": "eV"}, "volume": 42.3}
        contrib = _make_contribution_in(data=nested)
        assert contrib.data["band_gap"]["value"] == 1.5


# ---------------------------------------------------------------------------
# Contribution.from_input_model
# ---------------------------------------------------------------------------


class TestContributionFromInputModel:
    def test_is_public_forced_to_false(self):
        contrib_in = _make_contribution_in()
        contribution = Contribution.from_input_model(contrib_in)
        assert contribution.is_public is False

    def test_is_public_false_even_if_input_had_is_public(self):
        # ContributionIn (ContributionBase) has no is_public field, but we ensure
        # from_input_model always sets it to False on the resulting Contribution.
        contrib_in = _make_contribution_in()
        contribution = Contribution.from_input_model(contrib_in)
        assert contribution.is_public is False

    def test_fields_carried_over(self):
        contrib_in = _make_contribution_in(project="my-project", formula="SiO2")
        contribution = Contribution.from_input_model(contrib_in)
        assert contribution.project == "my-project"
        assert contribution.formula == "SiO2"

    def test_data_carried_over(self):
        data = {"key": "value"}
        contrib_in = _make_contribution_in(data=data)
        contribution = Contribution.from_input_model(contrib_in)
        assert contribution.data == data


# ---------------------------------------------------------------------------
# ContributionOut — optional fields
# ---------------------------------------------------------------------------


class TestContributionOut:
    def test_all_fields_optional(self):
        out = ContributionOut()
        assert out.id is None
        assert out.project is None
        assert out.formula is None
        assert out.is_public is None
        assert out.data is None

    def test_partial_population(self):
        out = ContributionOut(project="mp-proj", formula="Li2O")
        assert out.project == "mp-proj"
        assert out.formula == "Li2O"
        assert out.identifier is None

    def test_is_public_field(self):
        out = ContributionOut(is_public=True)
        assert out.is_public is True

    def test_data_field(self):
        data = {"energy": -3.5}
        out = ContributionOut(data=data)
        assert out.data == data


# ---------------------------------------------------------------------------
# ContributionPatch — sparse update model
# ---------------------------------------------------------------------------


class TestContributionPatch:
    def test_all_fields_optional(self):
        patch = ContributionPatch()
        assert patch.project is None
        assert patch.identifier is None
        assert patch.formula is None
        assert patch.data is None

    def test_partial_patch(self):
        patch = ContributionPatch(formula="Li2O", needs_build=False)
        assert patch.formula == "Li2O"
        assert patch.needs_build is False
        assert patch.project is None

    def test_data_can_be_set(self):
        patch = ContributionPatch(data={"new_key": 42})
        assert patch.data == {"new_key": 42}


# ---------------------------------------------------------------------------
# MongoDbContributionRepository._build_scope (pure logic, no DB needed)
# ---------------------------------------------------------------------------

_ADMIN = User(username="google:admin@example.com", groups=frozenset({"admin"}))
_ALICE = User(username="google:alice@example.com", groups=frozenset({"mp-team"}))
_ANON = User()


class TestContributionRepoScope:
    def test_admin_scope_is_empty(self):
        assert MongoDbContributionRepository._build_scope(_ADMIN) == {}

    def test_anon_scope_has_or_clause(self):
        scope = MongoDbContributionRepository._build_scope(_ANON)
        assert "$or" in scope

    def test_anon_scope_includes_is_public_true(self):
        ors = MongoDbContributionRepository._build_scope(_ANON)["$or"]
        assert any(c == {"is_public": True} for c in ors)

    def test_anon_scope_has_no_group_id_clause(self):
        ors = MongoDbContributionRepository._build_scope(_ANON)["$or"]
        assert not any("_id" in c for c in ors)

    def test_authed_user_scope_includes_is_public(self):
        ors = MongoDbContributionRepository._build_scope(_ALICE)["$or"]
        assert any(c == {"is_public": True} for c in ors)

    def test_authed_user_with_groups_has_group_id_clause(self):
        user = User(username="u@example.com", groups=frozenset({"g1", "g2"}))
        ors = MongoDbContributionRepository._build_scope(user)["$or"]
        group_clause = next((c for c in ors if "_id" in c), None)
        assert group_clause is not None
        assert set(group_clause["_id"]["$in"]) == {"g1", "g2"}

    def test_authed_user_no_groups_has_no_group_id_clause(self):
        user = User(username="u@example.com", groups=frozenset())
        ors = MongoDbContributionRepository._build_scope(user)["$or"]
        assert not any("_id" in c for c in ors)
