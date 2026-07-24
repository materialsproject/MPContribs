"""Unit tests for the contribution repository's dict merge/replace update helpers.

Covers the pure translation from a patch's field map to the ``$set`` document: with ``replace_data``
a dict field overwrites whole; without it, dict fields deep-merge into dotted ``$set`` paths so
unmentioned stored keys survive (an addition), stopping at atomic annotated-value leaves.
"""

from mpcontribs_api.domains.contributions.repository import (
    _build_update_set,
    _flatten_for_merge,
    _is_atomic_leaf,
)


class TestIsAtomicLeaf:
    def test_scalars_and_lists_are_atomic(self):
        assert _is_atomic_leaf(1)
        assert _is_atomic_leaf("x")
        assert _is_atomic_leaf([1, 2, 3])
        assert _is_atomic_leaf(None)

    def test_annotated_leaf_is_atomic(self):
        leaf = {"value": 1.0, "input_value": 1.0, "display": "1 eV", "unit": "eV"}
        assert _is_atomic_leaf(leaf)

    def test_plain_group_dict_is_not_atomic(self):
        assert not _is_atomic_leaf({"a": 1, "b": 2})

    def test_minimal_value_leaf_is_atomic(self):
        # A bare-number leaf has only ``value`` (no input_value/display) and is still a leaf.
        assert _is_atomic_leaf({"value": 1.0})
        assert _is_atomic_leaf({"value": 1.0, "input_value": 1.0})

    def test_dict_with_non_reserved_key_is_not_atomic(self):
        # A numeric ``value`` alongside a non-reserved key is a descendable group, not a leaf.
        assert not _is_atomic_leaf({"value": 1.0, "extra": 2})
        # ``value`` present but non-numeric -> not a leaf either.
        assert not _is_atomic_leaf({"value": "text"})


class TestFlattenForMerge:
    def test_top_level_scalars_become_dotted_paths(self):
        assert _flatten_for_merge("data", {"a": 1, "b": 2}) == {"data.a": 1, "data.b": 2}

    def test_nested_group_flattens_to_leaves(self):
        # A plain nested group is descended so sibling leaves are addressed individually and any
        # unmentioned sibling in the stored dict survives the merge.
        out = _flatten_for_merge("data", {"group": {"x": 1, "y": 2}})
        assert out == {"data.group.x": 1, "data.group.y": 2}

    def test_annotated_leaf_stays_whole(self):
        leaf = {"value": 4.2, "input_value": 4.2, "display": "4.2 eV", "unit": "eV"}
        out = _flatten_for_merge("data", {"bandgap": leaf})
        # Not descended into value/unit/... — the leaf is set atomically.
        assert out == {"data.bandgap": leaf}

    def test_empty_dict_contributes_nothing(self):
        assert _flatten_for_merge("data", {}) == {}
        assert _flatten_for_merge("data", {"group": {}}) == {}


class TestBuildUpdateSet:
    def test_replace_passes_through_verbatim(self):
        update = {"formula": "H2O", "data": {"a": 1}}
        assert _build_update_set(update, replace_data=True) == update

    def test_merge_flattens_only_dict_fields(self):
        update = {"formula": "H2O", "needs_build": False, "data": {"a": 1, "grp": {"b": 2}}}
        assert _build_update_set(update, replace_data=False) == {
            "formula": "H2O",
            "needs_build": False,
            "data.a": 1,
            "data.grp.b": 2,
        }

    def test_merge_keeps_list_fields_direct(self):
        update = {"structures": [{"$id": 1}]}
        assert _build_update_set(update, replace_data=False) == update

    def test_merge_of_only_empty_dict_yields_empty_document(self):
        # Signals the caller (update_contribution_by_identifiers) to treat the patch as a no-op
        # rather than issue an empty (and MongoDB-rejected) $set.
        assert _build_update_set({"data": {}}, replace_data=False) == {}
