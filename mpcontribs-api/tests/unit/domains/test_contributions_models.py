import pytest
from beanie import PydanticObjectId

from mpcontribs_api.authz import User
from mpcontribs_api.domains._shared.types import Identity
from mpcontribs_api.domains.contributions.models import (
    Contribution,
    ContributionFilter,
    ContributionIdentity,
    ContributionOut,
)
from mpcontribs_api.domains.contributions.repository import MongoDbContributionRepository
from mpcontribs_api.exceptions import DataKeyError, ValidationError


def _offenders(exc: DataKeyError) -> dict[str, str | None]:
    """Map each offending key from a DataKeyError to its suggested canonical spelling (or None)."""
    return {entry["key"]: entry["suggestion"] for entry in exc.context["offending_keys"]}


# The identity/index column order, declared once here so the tests fail loudly if the field order
# in ContributionIdentity ever drifts (which silently forces a Mongo index migration).
IDENTITY_FIELD_ORDER = [
    "project",
    "material_id",
    "chemical_system_id",
    "formula",
    "unique_value",
    "condition_key",
]


# ---------------------------------------------------------------------------
# Contribution — stored-document data validation
#
# Contributions are worker-written; the only remaining data validation on this server is the strict
# stored-key check applied when a Contribution document is built (ContributionStoredData).
# ---------------------------------------------------------------------------


class TestContributionStoredData:
    def test_canonical_keys_accepted(self):
        contrib = Contribution(_id=PydanticObjectId(), project="p", chemical_system_id="Fe-O", data={"goodKey": 1})
        assert contrib.data == {"goodKey": 1}

    def test_empty_and_absent_data(self):
        # Empty data is valid; optional identifiers may be omitted (no hierarchy check on stored docs).
        contrib = Contribution(_id=PydanticObjectId(), project="p", chemical_system_id="Fe-O", data={})
        assert contrib.data == {}
        assert contrib.material_id is None
        assert contrib.formula is None

    def test_non_canonical_plain_key_rejected(self):
        # Stored keys must be canonical plain keys at every level (no dotted/annotated grammar).
        with pytest.raises(DataKeyError) as exc:
            Contribution(_id=PydanticObjectId(), project="p", chemical_system_id="Fe-O", data={"bad.key": 1})
        assert _offenders(exc.value) == {"bad.key": "badKey"}

    def test_reserved_leaf_key_rejected_when_nested(self):
        with pytest.raises(DataKeyError) as exc:
            Contribution(
                _id=PydanticObjectId(), project="p", chemical_system_id="Fe-O", data={"group": {"unit": "x"}}
            )
        assert exc.value.context["offending_keys"] == [{"key": "unit", "suggestion": None, "reason": "reserved"}]

    def test_is_public_defaults_false(self):
        contrib = Contribution(_id=PydanticObjectId(), project="p", chemical_system_id="Fe-O", data={})
        assert contrib.is_public is False
        assert contrib.structures is None
        assert contrib.tables is None
        assert contrib.attachments is None


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


class TestContributionOutDefaultFields:
    def test_default_fields_are_identity_and_metadata(self):
        assert ContributionOut.default_fields() == (
            "id",
            "project",
            "material_id",
            "chemical_system_id",
            "formula",
            "unique_value",
            "is_public",
            "last_modified",
        )


# ---------------------------------------------------------------------------
# MongoDbContributionRepository.read_scope (pure logic, no DB needed)
# ---------------------------------------------------------------------------

_ADMIN = User(username="google:admin@example.com", groups=frozenset({"admin"}))
_ALICE = User(username="google:alice@example.com", groups=frozenset({"mp-team"}))
_ANON = User()


class TestContributionRepoScope:
    def test_admin_scope_is_empty(self):
        assert MongoDbContributionRepository.read_scope.query(_ADMIN) == {}

    def test_anon_scope_has_or_clause(self):
        scope = MongoDbContributionRepository.read_scope.query(_ANON)
        assert "$or" in scope

    def test_anon_scope_includes_is_public_true(self):
        ors = MongoDbContributionRepository.read_scope.query(_ANON)["$or"]
        assert any(c == {"is_public": True} for c in ors)

    def test_anon_scope_has_no_group_id_clause(self):
        ors = MongoDbContributionRepository.read_scope.query(_ANON)["$or"]
        assert not any("_id" in c for c in ors)

    def test_authed_user_scope_includes_is_public(self):
        ors = MongoDbContributionRepository.read_scope.query(_ALICE)["$or"]
        assert any(c == {"is_public": True} for c in ors)

    def test_authed_user_with_groups_has_group_id_clause(self):
        user = User(username="u@example.com", groups=frozenset({"g1", "g2"}))
        ors = MongoDbContributionRepository.read_scope.query(user)["$or"]
        group_clause = next((c for c in ors if "project" in c), None)
        assert group_clause is not None
        assert set(group_clause["project"]["$in"]) == {"g1", "g2"}

    def test_authed_user_no_groups_has_no_group_id_clause(self):
        user = User(username="u@example.com", groups=frozenset())
        ors = MongoDbContributionRepository.read_scope.query(user)["$or"]
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

    # A malformed id must surface as a controlled ValidationError (422), not leak
    # bson.errors.InvalidId (an unmapped 500), matching MongoDbRepository._convert_object_id.
    def test_malformed_id_raises_validation_error(self):
        with pytest.raises(ValidationError):
            ContributionFilter(id="not-an-object-id")


# ---------------------------------------------------------------------------
# ContributionIdentity — the concrete identity dataclass (renamed from Identity,
# which is now the shared abstract base holding the index/projection machinery)
# ---------------------------------------------------------------------------


def _identity(**overrides) -> ContributionIdentity:
    """A fully-populated ContributionIdentity, overridable per test."""
    defaults: dict = {
        "project": "proj",
        "material_id": "mp-1",
        "chemical_system_id": "Fe-O",
        "formula": "Fe2O3",
        "unique_value": None,
        "condition_key": "",
    }
    defaults.update(overrides)
    return ContributionIdentity(**defaults)


class TestContributionIdentityStructure:
    def test_is_concrete_subclass_of_identity_abc(self):
        # Identity is the abstract base; ContributionIdentity is the concrete, field-bearing subclass.
        assert issubclass(ContributionIdentity, Identity)
        assert ContributionIdentity is not Identity

    def test_field_order_matches_index_and_projection(self):
        # Field declaration order IS the index column order — reordering silently forces a Mongo
        # index migration, so index_model keys, projection keys, and as_dict all pin the same order.
        index_keys = [key for key, _direction in ContributionIdentity.index_model().document["key"].items()]
        assert index_keys == IDENTITY_FIELD_ORDER
        assert list(ContributionIdentity.projection().keys()) == IDENTITY_FIELD_ORDER
        assert list(_identity().as_dict().keys()) == IDENTITY_FIELD_ORDER

    def test_hierarchy_fields_are_the_identifier_triple(self):
        assert ContributionIdentity.HIERARCHY_FIELDS == frozenset({"material_id", "chemical_system_id", "formula"})


class TestContributionIdentityIndexModel:
    def test_default_index_is_named_and_unique(self):
        index = ContributionIdentity.index_model()
        # Neutral default; each collection passes an explicit name matching its deployed index.
        assert index.document["name"] == "identity"
        assert index.document["unique"] is True

    def test_explicit_name_is_used(self):
        # Contributions keeps its deployed index name by passing it explicitly.
        assert ContributionIdentity.index_model(name="project_identity").document["name"] == "project_identity"

    def test_unique_can_be_disabled(self):
        assert ContributionIdentity.index_model(unique=False).document["unique"] is False


class TestContributionIdentityProjection:
    def test_projection_selects_exactly_the_identity_fields(self):
        assert ContributionIdentity.projection() == dict.fromkeys(IDENTITY_FIELD_ORDER, 1)


class TestContributionIdentityAsDict:
    def test_as_dict_is_flat_and_keyed_by_field_name(self):
        identity = _identity(unique_value="A", condition_key="cond")
        assert identity.as_dict() == {
            "project": "proj",
            "material_id": "mp-1",
            "chemical_system_id": "Fe-O",
            "formula": "Fe2O3",
            "unique_value": "A",
            "condition_key": "cond",
        }


class TestContributionIdentityFromDocument:
    def test_full_document_round_trips(self):
        identity = _identity(unique_value="A", condition_key="cond")
        assert ContributionIdentity.from_document(identity.as_dict()) == identity

    def test_null_stripped_document_falls_back_to_defaults(self):
        # Contributions are stored with keep_nulls=False, so a chem-system-only contribution's
        # projected identity doc omits material_id/formula/unique_value/condition_key entirely.
        rebuilt = ContributionIdentity.from_document({"project": "proj", "chemical_system_id": "Fe-O"})
        assert rebuilt == ContributionIdentity(
            project="proj",
            material_id=None,
            chemical_system_id="Fe-O",
            formula=None,
            unique_value=None,
            condition_key="",
        )

    def test_explicit_null_is_treated_as_absent(self):
        # A doc that carries an explicit null (rather than omitting the key) resolves identically.
        rebuilt = ContributionIdentity.from_document(
            {"project": "proj", "material_id": None, "chemical_system_id": "Fe-O", "formula": None}
        )
        assert rebuilt.material_id is None
        assert rebuilt.formula is None

    def test_missing_required_non_null_field_raises(self):
        # project and chemical_system_id are non-null identity fields; their absence is data
        # corruption, so from_document surfaces it as a TypeError rather than fabricating a value.
        with pytest.raises(TypeError):
            ContributionIdentity.from_document({"chemical_system_id": "Fe-O"})  # no project
        with pytest.raises(TypeError):
            ContributionIdentity.from_document({"project": "proj"})  # no chemical_system_id


class TestContributionIdentityEqualityAndHashing:
    """Identity equality/hashing is what powers conflict dedup over stored identities."""

    def test_identical_identities_are_equal_and_collapse_in_a_set(self):
        assert _identity() == _identity()
        assert len({_identity(), _identity()}) == 1

    def test_same_triple_distinct_unique_value_are_different_identities(self):
        # The whole point of unique_value: same (project, ids) but a distinct discriminator is a
        # distinct identity, so both survive as separate members and neither conflicts.
        a = _identity(unique_value="A")
        b = _identity(unique_value="B")
        assert a != b
        assert len({a, b}) == 2

    def test_identity_is_frozen(self):
        with pytest.raises(Exception):  # noqa: B017,PT011 -- dataclasses.FrozenInstanceError
            _identity().project = "other"  # type: ignore[misc]


class TestContributionIdentityCheckHierarchy:
    """check_hierarchy enforces chemical_system_id > formula > material_id (shared ABC logic)."""

    def test_full_identifier_stack_passes(self):
        ContributionIdentity.check_hierarchy("mp-1", "Fe-O", "Fe2O3")

    def test_chemical_system_only_passes(self):
        ContributionIdentity.check_hierarchy(None, "Fe-O", None)

    def test_missing_chemical_system_is_rejected(self):
        with pytest.raises(ValidationError, match="chemical_system_id is required"):
            ContributionIdentity.check_hierarchy(None, None, "Fe2O3")

    def test_material_id_without_formula_is_rejected(self):
        with pytest.raises(ValidationError, match="formula is required"):
            ContributionIdentity.check_hierarchy("mp-1", "Fe-O", None)

    def test_formula_without_material_id_is_allowed(self):
        ContributionIdentity.check_hierarchy(None, "Fe-O", "Fe2O3")
