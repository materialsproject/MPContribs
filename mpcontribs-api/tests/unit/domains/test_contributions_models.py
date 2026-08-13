from datetime import UTC, datetime

import pytest
from beanie import PydanticObjectId
from pydantic import ValidationError as PydanticValidationError

from mpcontribs_api.authz import User
from mpcontribs_api.domains.contributions.repository import MongoDbContributionRepository

from mpcontribs_api.domains.contributions.models import (
    Contribution,
    ContributionFilter,
    ContributionIn,
    ContributionOut,
    ContributionPatch,
    extract_unique_value,
)
from mpcontribs_api.exceptions import ValidationError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_contribution_in(**overrides) -> ContributionIn:
    """Build a minimal valid ContributionIn for testing."""
    defaults: dict = {
        "_id": PydanticObjectId(),
        "project": "test-project",
        "material_id": "mp-1234",
        "chemical_system_id": "Fe-O",
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
                "material_id": "mp-001",
                "chemical_system_id": "Fe-O",
                "formula": "Fe2O3",
                "data": {},
            }
        )
        assert contrib.project == "mp-project"
        # material_id is normalized on input: leading zeros in the numeric part are trimmed.
        assert contrib.material_id == "mp-1"
        assert contrib.chemical_system_id == "Fe-O"
        assert contrib.formula == "Fe2O3"
        assert contrib.data == {}

    def test_defaults(self):
        contrib = _make_contribution_in()
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
                    "material_id": "mp-001",
                    "chemical_system_id": "Fe-O",
                    "formula": "Fe",
                    "data": {},
                }
            )

    def test_formula_optional_when_no_material_id(self):
        # formula is no longer unconditionally required: a chemical-system-level contribution is
        # valid (identifier hierarchy: chemical_system_id > formula > material_id).
        contrib = ContributionIn(
            **{
                "_id": PydanticObjectId(),
                "project": "proj",
                "chemical_system_id": "Fe-O",
                "data": {},
            }
        )
        assert contrib.formula is None
        assert contrib.material_id is None

    def test_data_can_be_empty_dict(self):
        contrib = _make_contribution_in(data={})
        assert contrib.data == {}

    def test_data_accepts_nested_structure(self):
        nested = {"band_gap": {"value": 1.5, "unit": "eV"}, "volume": 42.3}
        contrib = _make_contribution_in(data=nested)
        assert contrib.data["band_gap"]["value"] == 1.5

    def test_data_depth_validation(self):
        max_nesting = {"lvl_1": {"lvl_2": {"lvl_3": {"lvl_4": {"lvl_5": {"lvl_6": {"lvl_7": "pass"}}}}}}}
        invalid_nesting = {"lvl_1": {"lvl_2": {"lvl_3": {"lvl_4": {"lvl_5": {"lvl_6": {"lvl_7": {"lvl_8": "fail"}}}}}}}}
        _make_contribution_in(data=max_nesting)
        assert True
        with pytest.raises(ValidationError, match="Depth of Contribution.data"):
            _make_contribution_in(data=invalid_nesting)

    def test_data_key_validation(self):
        valid_punctuation = {"test*/|": "pass"}
        invalid_punctuation = {"test.": "fail"}
        too_many_pipes = {"test||": "fail"}
        non_ascii = {"ΔE": "fail"}
        _make_contribution_in(data=valid_punctuation)
        assert True
        with pytest.raises(ValidationError, match="Punctuation found in Contribution.data keys"):
            _make_contribution_in(data=invalid_punctuation)
        with pytest.raises(ValidationError, match="Punctuation found in Contribution.data keys"):
            _make_contribution_in(data=too_many_pipes)
        with pytest.raises(ValidationError, match="Non-ASCII key found in Contribution.data"):
            _make_contribution_in(data=non_ascii)

    # There isn't currently value validation. This is to check that that is true
    def test_data_value_validation(self):
        pipes_in_values = {"test": "pass||"}
        punctuation_in_values = {"test": "pass."}
        ascii_in_values = {"test": "Δ"}
        _make_contribution_in(data=pipes_in_values)
        _make_contribution_in(data=punctuation_in_values)
        _make_contribution_in(data=ascii_in_values)
        assert True


# ---------------------------------------------------------------------------
# Contribution identifier validation (material_id / chemical_system_id / formula)
#
# Validation lives on the input models (ContributionIn / ContributionPatch), not the stored
# Contribution, so these exercise it through ContributionIn.
# ---------------------------------------------------------------------------


class TestMaterialIdValidation:
    @pytest.mark.parametrize(
        ("given", "expected"),
        [
            # Numeric (MpId) form: leading zeros trimmed.
            ("mp-149", "mp-149"),
            ("mp-1234567", "mp-1234567"),
            ("mp-001", "mp-1"),  # leading zeros trimmed
            ("mp-0001234", "mp-1234"),
            ("  mp-42  ", "mp-42"),  # surrounding whitespace stripped
            ("MP-149", "mp-149"),  # prefix lowercased
            # Alphabetic (AlphaId) form: left-padded with 'a' to a fixed width of 8, never stripped.
            ("mp-abcdefgh", "mp-abcdefgh"),  # already full width, unchanged
            ("mp-b", "mp-aaaaaaab"),  # dropped leading 'a's re-padded by us
            ("mp-bcd", "mp-aaaaabcd"),
            ("mp-abc", "mp-aaaaaabc"),  # a leading 'a' is significant, not stripped
            ("mp-aaaaaabc", "mp-aaaaaabc"),  # explicit padding is idempotent
            ("MP-abc", "mp-aaaaaabc"),  # prefix lowercased
            ("mp-ABC", "mp-aaaaaabc"),  # letters lowercased
            ("mp-a", "mp-aaaaaaaa"),  # single letter padded to full width
            ("  mp-xyz  ", "mp-aaaaaxyz"),  # surrounding whitespace stripped
        ],
    )
    def test_valid_material_id_is_normalized(self, given, expected):
        assert _make_contribution_in(material_id=given).material_id == expected

    @pytest.mark.parametrize(
        "bad",
        [
            "mp-12345678",  # too many significant digits
            "mp-",  # empty body
            "mp-1a",  # mixed digits and letters
            "1234",  # missing prefix
            "mvc-1",  # wrong prefix
            "mp-1.0",  # non-integer
            "mp-abcdefghi",  # 9 letters, one over the cap
        ],
    )
    def test_invalid_material_id_raises(self, bad):
        with pytest.raises(ValidationError, match="material_id"):
            _make_contribution_in(material_id=bad)


class TestChemicalSystemIdValidation:
    @pytest.mark.parametrize("good", ["Fe-O", "Li-Fe-O", "Fe", "H"])
    def test_valid_chemical_system_id(self, good):
        assert _make_contribution_in(chemical_system_id=good).chemical_system_id == good

    @pytest.mark.parametrize(
        ("given", "expected"),
        [
            ("fe-o", "Fe-O"),  # all lowercase
            ("FE-O", "Fe-O"),  # all uppercase
            ("fE-o", "Fe-O"),  # mixed case
            ("li-FE-o", "Li-Fe-O"),
            ("h", "H"),
        ],
    )
    def test_chemical_system_id_case_is_normalized(self, given, expected):
        assert _make_contribution_in(chemical_system_id=given).chemical_system_id == expected

    @pytest.mark.parametrize("bad", ["Xx-O", "Fe-", "-Fe", "Fe--O", ""])
    def test_invalid_chemical_system_id_raises(self, bad):
        with pytest.raises(ValidationError, match="chemical_system_id"):
            _make_contribution_in(chemical_system_id=bad)


class TestFormulaValidation:
    @pytest.mark.parametrize(
        ("given", "expected"),
        [
            ("Fe2O3", "Fe2O3"),
            ("LiFeO2", "LiFeO2"),
            ("Fe", "Fe"),
            ("Fe02O3", "Fe2O3"),  # leading zeros in counts trimmed
            ("FeO03", "FeO3"),
            ("Si0.2Fe0.1C4", "Si0.2Fe0.1C4"),
            ("Si00.04", "Si0.04"),
            ("Fe0.1", "Fe0.1"),
            ("Fe.1", "Fe0.1"),
            ("Fe00.1", "Fe0.1"),
            ("Fe2.0O3", "Fe2O3"),
            ("Fe0.20O3", "Fe0.2O3"),
            ("Fe₂O₃", "Fe2O3"),
            ("Co³O₄", "Co3O4"),
            ("Ｆｅ２Ｏ３", "Fe2O3"),
        ],
    )
    def test_valid_formula_is_normalized(self, given, expected):
        assert _make_contribution_in(formula=given).formula == expected

    @pytest.mark.parametrize(
        "bad",
        [
            "X",
            "fe2",
            "Fe2xO",
            "2FeO",
            "Fe0",
            "",
            "Si0.0.4",
            "Si0,1",
            "Si0.0",
            "Si.",
        ],
    )
    def test_invalid_formula_raises(self, bad):
        with pytest.raises(ValidationError, match="formula"):
            _make_contribution_in(formula=bad)


class TestPatchIdentifierValidation:
    def test_patch_normalizes_material_id(self):
        assert ContributionPatch(material_id="mp-007").material_id == "mp-7"

    def test_patch_normalizes_formula(self):
        assert ContributionPatch(formula="Fe02O3").formula == "Fe2O3"

    def test_patch_rejects_bad_chemical_system_id(self):
        with pytest.raises(ValidationError, match="chemical_system_id"):
            ContributionPatch(chemical_system_id="Zz")

    def test_patch_identifiers_stay_optional(self):
        patch = ContributionPatch(is_public=True)
        assert patch.material_id is None
        assert patch.chemical_system_id is None
        assert patch.formula is None


class TestIdentifierHierarchy:
    """chemical_system_id > formula > material_id: each level requires the ones above it."""

    def _build(self, **identity):
        return ContributionIn(_id=PydanticObjectId(), project="proj", data={}, **identity)

    def test_chemical_system_only_is_valid(self):
        contrib = self._build(chemical_system_id="Fe-O")
        assert contrib.chemical_system_id == "Fe-O"
        assert contrib.formula is None
        assert contrib.material_id is None

    def test_chemical_system_and_formula_is_valid(self):
        contrib = self._build(chemical_system_id="Fe-O", formula="Fe2O3")
        assert contrib.formula == "Fe2O3"
        assert contrib.material_id is None

    def test_full_triple_is_valid(self):
        contrib = self._build(chemical_system_id="Fe-O", formula="Fe2O3", material_id="mp-1")
        assert contrib.material_id == "mp-1"

    def test_material_id_without_formula_raises(self):
        with pytest.raises(ValidationError, match="formula is required when material_id"):
            self._build(chemical_system_id="Fe-O", material_id="mp-1")

    def test_missing_chemical_system_raises(self):
        # chemical_system_id is required by its type, so omitting it is a Pydantic error.
        with pytest.raises(PydanticValidationError):
            self._build(formula="Fe2O3")


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
        assert out.material_id is None
        assert out.unique_value is None

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
        assert patch.material_id is None
        assert patch.chemical_system_id is None
        assert patch.formula is None
        assert patch.data is None

    def test_partial_patch(self):
        patch = ContributionPatch(formula="Li2O", needs_build=False)
        assert patch.formula == "Li2O"
        assert patch.project is None

    def test_data_can_be_set(self):
        patch = ContributionPatch(data={"new_key": 42})
        assert patch.data == {"new_key": 42}


# ---------------------------------------------------------------------------
# extract_unique_value — promoting a project's unique_column to the identity value
# ---------------------------------------------------------------------------


class TestExtractUniqueValue:
    def test_top_level_scalar(self):
        assert extract_unique_value({"sample_id": "A"}, "sample_id") == "A"

    def test_nested_dotted_path(self):
        assert extract_unique_value({"conditions": {"temp": 300}}, "conditions.temp") == 300

    def test_accepts_bool_and_float(self):
        assert extract_unique_value({"flag": True}, "flag") is True
        assert extract_unique_value({"x": 1.5}, "x") == 1.5

    def test_missing_path_raises(self):
        with pytest.raises(ValidationError, match="missing from Contribution.data"):
            extract_unique_value({"other": 1}, "sample_id")

    def test_missing_when_data_none_raises(self):
        with pytest.raises(ValidationError):
            extract_unique_value(None, "sample_id")

    def test_non_scalar_dict_raises(self):
        with pytest.raises(ValidationError, match="must resolve to a scalar"):
            extract_unique_value({"sample_id": {"nested": 1}}, "sample_id")

    def test_non_scalar_list_raises(self):
        with pytest.raises(ValidationError, match="must resolve to a scalar"):
            extract_unique_value({"sample_id": [1, 2]}, "sample_id")


class TestContributionOutDefaultFields:
    def test_default_fields_are_identity_and_metadata(self):
        assert ContributionOut.default_fields() == [
            "id",
            "project",
            "material_id",
            "chemical_system_id",
            "formula",
            "unique_value",
            "is_public",
            "last_modified",
        ]


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
        group_clause = next((c for c in ors if "project" in c), None)
        assert group_clause is not None
        assert set(group_clause["project"]["$in"]) == {"g1", "g2"}

    def test_authed_user_no_groups_has_no_group_id_clause(self):
        user = User(username="u@example.com", groups=frozenset())
        ors = MongoDbContributionRepository._build_scope(user)["$or"]
        assert not any("_id" in c for c in ors)


# ---------------------------------------------------------------------------
# ContributionFilter.convert_str_to_oid
# ---------------------------------------------------------------------------


class TestContributionFilterIdValidator:
    def test_empty_filter_id_is_none(self):
        assert ContributionFilter().id is None

    def test_str_converted_to_object_id(self):
        oid = PydanticObjectId()
        filter = ContributionFilter(id=str(oid))
        assert isinstance(filter.id, PydanticObjectId)
        assert filter.id == oid

    def test_object_id_passthrough(self):
        oid = PydanticObjectId()
        assert ContributionFilter(id=oid).id == oid

    # RED: a malformed id currently leaks bson.errors.InvalidId (not a
    # ValueError subclass), which the exception handlers don't map — so
    # `DELETE /contributions/{bad-id}` would 500 instead of 422. Intended
    # behavior is a controlled validation error, matching how
    # MongoDbRepository._convert_object_id handles the same input.
    def test_malformed_id_raises_validation_error(self):
        with pytest.raises(ValidationError):
            ContributionFilter(id="not-an-object-id")
