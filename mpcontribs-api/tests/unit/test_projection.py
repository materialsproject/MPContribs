from typing import Any

import pytest
from pydantic import BaseModel, Field

from mpcontribs_api.exceptions import ValidationError as AppValidationError
from mpcontribs_api.projection import (
    SparseFieldsModel,
    _classify,
    _collapse,
    _unwrap_optional,
    _validate_path,
    _walk_path,
)

# ---------------------------------------------------------------------------
# Helpers — simple models used across tests
# ---------------------------------------------------------------------------


class Address(BaseModel):
    street: str
    city: str
    country: str | None = None


class Simple(SparseFieldsModel):
    name: str
    age: int
    score: float | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    address: Address | None = None


# ---------------------------------------------------------------------------
# _unwrap_optional
# ---------------------------------------------------------------------------


class TestUnwrapOptional:
    def test_strips_none(self):
        result = _unwrap_optional(str | None)
        assert result is str

    def test_plain_annotation_unchanged(self):
        result = _unwrap_optional(str)
        assert result is str

    def test_optional_model(self):
        result = _unwrap_optional(Address | None)
        assert result is Address

    def test_union_without_none_unchanged(self):
        # int | str has no None — returned as-is
        result = _unwrap_optional(int | str)
        assert result == (int | str)


# ---------------------------------------------------------------------------
# _classify
# ---------------------------------------------------------------------------


class TestClassify:
    def test_base_model_subclass(self):
        kind, model = _classify(Address)
        assert kind == "model"
        assert model is Address

    def test_optional_model(self):
        kind, model = _classify(Address | None)
        assert kind == "model"
        assert model is Address

    def test_dict_annotation(self):
        kind, model = _classify(dict)
        assert kind == "dict"
        assert model is None

    def test_dict_generic(self):
        kind, model = _classify(dict[str, Any])
        assert kind == "dict"
        assert model is None

    def test_list_annotation(self):
        kind, model = _classify(list[str])
        assert kind == "list"
        assert model is None

    def test_scalar_str(self):
        kind, model = _classify(str)
        assert kind == "scalar"
        assert model is None

    def test_scalar_int(self):
        kind, model = _classify(int)
        assert kind == "scalar"
        assert model is None

    def test_any(self):
        kind, model = _classify(Any)
        assert kind == "dict"
        assert model is None


# ---------------------------------------------------------------------------
# _collapse
# ---------------------------------------------------------------------------


class TestCollapse:
    def test_no_overlap(self):
        paths = frozenset({"name", "age"})
        assert _collapse(paths) == paths

    def test_parent_subsumes_child(self):
        paths = frozenset({"address", "address.city"})
        assert _collapse(paths) == frozenset({"address"})

    def test_child_without_parent_kept(self):
        paths = frozenset({"address.city"})
        assert _collapse(paths) == paths

    def test_multiple_children_of_same_parent(self):
        paths = frozenset({"address", "address.city", "address.street"})
        assert _collapse(paths) == frozenset({"address"})

    def test_disjoint_nested_paths(self):
        paths = frozenset({"address.city", "name"})
        assert _collapse(paths) == paths

    def test_single_path(self):
        paths = frozenset({"name"})
        assert _collapse(paths) == paths

    def test_empty(self):
        assert _collapse(frozenset()) == frozenset()


# ---------------------------------------------------------------------------
# _walk_path
# ---------------------------------------------------------------------------


class TestWalkPath:
    def test_scalar_field(self):
        steps = list(_walk_path(Simple, "name"))
        assert len(steps) == 1
        assert steps[0].segment == "name"
        assert steps[0].kind == "scalar"
        assert steps[0].is_last is True

    def test_nested_model_field(self):
        steps = list(_walk_path(Simple, "address.city"))
        assert steps[0].segment == "address"
        assert steps[0].kind == "model"
        assert steps[0].is_last is False
        assert steps[1].segment == "city"
        assert steps[1].kind == "scalar"
        assert steps[1].is_last is True

    def test_unknown_field(self):
        steps = list(_walk_path(Simple, "nonexistent"))
        assert steps[0].kind == "unknown"

    def test_dict_field_goes_opaque(self):
        steps = list(_walk_path(Simple, "metadata.arbitrary_key"))
        assert steps[0].kind == "dict"
        assert steps[1].kind == "opaque"


# ---------------------------------------------------------------------------
# _validate_path
# ---------------------------------------------------------------------------


class TestValidatePath:
    def test_valid_scalar_path(self):
        _validate_path(Simple, "name")  # should not raise

    def test_valid_nested_path(self):
        _validate_path(Simple, "address.city")  # should not raise

    def test_valid_dict_path(self):
        _validate_path(Simple, "metadata.anything")  # opaque — allowed

    def test_unknown_top_level_raises(self):
        with pytest.raises(AppValidationError, match="unknown field"):
            _validate_path(Simple, "nonexistent")

    def test_subfield_of_scalar_raises(self):
        with pytest.raises(AppValidationError, match="cannot select subfields"):
            _validate_path(Simple, "name.sub")

    def test_subfield_of_list_raises(self):
        with pytest.raises(AppValidationError, match="cannot select subfields"):
            _validate_path(Simple, "tags.sub")


# ---------------------------------------------------------------------------
# SparseFieldsModel.field_names
# ---------------------------------------------------------------------------


class TestFieldNames:
    def test_returns_top_level_fields(self):
        names = Simple.field_names()
        assert "name" in names
        assert "age" in names
        assert "address" in names
        assert "metadata" in names

    def test_does_not_include_nested(self):
        names = Simple.field_names()
        assert "city" not in names
        assert "street" not in names


# ---------------------------------------------------------------------------
# SparseFieldsModel.parse_fields
# ---------------------------------------------------------------------------


class TestParseFields:
    def test_none_returns_none(self):
        assert Simple.parse_fields(None) is None

    def test_empty_list_returns_none(self):
        assert Simple.parse_fields([]) is None

    def test_single_valid_field(self):
        result = Simple.parse_fields(["name"])
        assert result is not None
        assert "name" in result

    def test_multiple_fields(self):
        result = Simple.parse_fields(["name", "age"])
        assert result is not None
        assert "name" in result
        assert "age" in result

    def test_whitespace_stripped(self):
        result = Simple.parse_fields([" name ", " age "])
        assert result is not None
        assert "name" in result
        assert "age" in result

    def test_nested_field(self):
        result = Simple.parse_fields(["address.city"])
        assert result is not None
        assert "address.city" in result

    def test_parent_collapses_child(self):
        result = Simple.parse_fields(["address", "address.city"])
        assert result is not None
        assert "address" in result
        assert "address.city" not in result

    def test_unknown_field_raises(self):
        with pytest.raises(AppValidationError, match="unknown field"):
            Simple.parse_fields(["nonexistent"])

    def test_scalar_subfield_raises(self):
        with pytest.raises(AppValidationError, match="cannot select subfields"):
            Simple.parse_fields(["name.sub"])

    def test_sparse_always_always_included(self):
        class WithAlways(SparseFieldsModel):
            id: str | None = None
            name: str | None = None
            sparse_always = frozenset({"id"})

        result = WithAlways.parse_fields(["name"])
        assert result is not None
        assert "id" in result
        assert "name" in result


# ---------------------------------------------------------------------------
# SparseFieldsModel.projection
# ---------------------------------------------------------------------------


class TestProjection:
    def test_none_fields_returns_self(self):
        assert Simple.projection(None) is Simple

    def test_with_fields_returns_different_model(self):
        fields = Simple.parse_fields(["name"])
        result = Simple.projection(fields)
        assert result is not Simple

    def test_projected_model_has_settings_with_projection(self):
        fields = Simple.parse_fields(["name"])
        projected = Simple.projection(fields)
        assert hasattr(projected, "Settings")
        assert hasattr(projected.Settings, "projection")

    def test_projection_includes_id(self):
        fields = Simple.parse_fields(["name"])
        projected = Simple.projection(fields)
        assert "_id" in projected.Settings.projection

    def test_projection_caching(self):
        fields = Simple.parse_fields(["name"])
        first = Simple.projection(fields)
        second = Simple.projection(fields)
        assert first is second


# ---------------------------------------------------------------------------
# SparseFieldsModel._identity_fields
# ---------------------------------------------------------------------------


class TestIdentityFields:
    def test_field_with_id_alias_detected(self):
        class WithId(SparseFieldsModel):
            id: str | None = Field(default=None, alias="_id", serialization_alias="id")
            name: str | None = None

        identity = WithId._identity_fields()
        assert "id" in identity

    def test_no_id_field_returns_empty(self):
        identity = Simple._identity_fields()
        assert identity == frozenset()
