"""Unit tests for the contribution data merge helpers.

Covers the additive-merge translation of a patch's ``data`` against the *stored* shape:
``flatten_merge_paths`` produces the dotted ``$set`` paths Mongo receives, and ``merge_data`` produces
the equivalent post-write view used to resolve identity. Both follow one rule — a patch onto a stored
quantity leaf re-derives the whole leaf (so its canonical and ``input_*`` halves stay in sync, see
``patch_leaf``), a plain group is descended so unmentioned siblings survive, and any other scalar
sets its path directly. Precise SI-conversion behavior of ``patch_leaf`` is covered in ``test_units``.
"""

from mpcontribs_api.domains._shared.units import QuantityLeaf

# A stored leaf submitted as "2 m" (metre is an SI base unit, so canonical == submitted).
LEAF = QuantityLeaf.from_submission(2.0, "m").as_dict()

# The merge helpers now live on QuantityLeaf; aliased here to keep the test bodies readable.
flatten_merge_paths = QuantityLeaf.flatten_merge_paths
merge_data = QuantityLeaf.merge_data


class TestIsLeafFragment:
    def test_reserved_only_dict_is_a_fragment(self):
        assert QuantityLeaf.is_fragment({"unit": "kg"})
        assert QuantityLeaf.is_fragment({"value": 5, "unit": "kg"})
        assert QuantityLeaf.is_fragment({"error": 0.1})

    def test_non_reserved_or_empty_is_not_a_fragment(self):
        assert not QuantityLeaf.is_fragment({"unit": "kg", "x": 1})  # mixed reserved + plain
        assert not QuantityLeaf.is_fragment({"x": 1})
        assert not QuantityLeaf.is_fragment({})
        assert not QuantityLeaf.is_fragment(5)
        assert not QuantityLeaf.is_fragment("eV")


class TestFlattenMergePaths:
    def test_new_scalar_key_sets_directly(self):
        assert flatten_merge_paths({}, {"y": 9}, prefix="data.") == {"data.y": 9}

    def test_leaf_patch_sets_the_whole_recomputed_leaf(self):
        # A fragment touching a stored leaf writes the whole re-derived leaf at its path (not a
        # sub-path), so value/unit/error and input_* can be re-synced together. Changing the unit to
        # km re-converts the magnitude (2 m -> input 2 km -> 2000 m) and updates input_unit.
        out = flatten_merge_paths({"bandgap": LEAF}, {"bandgap": {"unit": "km"}}, prefix="data.")
        assert set(out) == {"data.bandgap"}  # whole leaf, not data.bandgap.unit
        assert out["data.bandgap"] == QuantityLeaf.patch_leaf(LEAF, {"unit": "km"})
        assert out["data.bandgap"]["value"] == 2000.0
        assert out["data.bandgap"]["input_unit"] == "km"

    def test_bare_scalar_onto_leaf_updates_magnitude(self):
        # A bare scalar is the new submitted magnitude; the leaf is re-derived, keeping the unit.
        out = flatten_merge_paths({"bandgap": LEAF}, {"bandgap": 5.0}, prefix="data.")
        assert out == {"data.bandgap": QuantityLeaf.patch_leaf(LEAF, {"value": 5.0})}
        assert out["data.bandgap"]["input_value"] == 5.0
        assert out["data.bandgap"]["unit"] == "m"

    def test_plain_group_descends_and_keeps_siblings(self):
        assert flatten_merge_paths({"grp": {"a": 1}}, {"grp": {"b": 2}}, prefix="data.") == {"data.grp.b": 2}

    def test_bare_scalar_onto_non_leaf_sets_directly(self):
        # Target is a plain group (not a quantity leaf) -> no leaf recompute, set the path itself.
        assert flatten_merge_paths({"grp": {"a": 1}}, {"grp": 7}, prefix="data.") == {"data.grp": 7}

    def test_new_leaf_shaped_value_onto_absent_key_descends(self):
        # No stored leaf to re-sync against -> ordinary descent (stored raw, canonicalized on insert).
        assert flatten_merge_paths({}, {"q": {"value": 3, "unit": "m"}}, prefix="data.") == {
            "data.q.value": 3,
            "data.q.unit": "m",
        }

    def test_empty_dict_contributes_nothing(self):
        assert flatten_merge_paths({"grp": {"a": 1}}, {"grp": {}}, prefix="data.") == {}


class TestMergeData:
    def test_leaf_patch_matches_flatten(self):
        # merge_data is the post-write view flatten_merge_paths would produce, key by key.
        merged = merge_data({"bandgap": LEAF}, {"bandgap": {"unit": "km"}})
        assert merged["bandgap"] == QuantityLeaf.patch_leaf(LEAF, {"unit": "km"})

    def test_bare_scalar_rederives_leaf(self):
        merged = merge_data({"bandgap": LEAF}, {"bandgap": 5.0})
        assert merged["bandgap"] == QuantityLeaf.patch_leaf(LEAF, {"value": 5.0})

    def test_new_key_and_sibling_survival(self):
        merged = merge_data({"x": 1, "grp": {"a": 1}}, {"y": 2, "grp": {"b": 2}})
        assert merged == {"x": 1, "y": 2, "grp": {"a": 1, "b": 2}}

    def test_none_base_treated_as_empty(self):
        assert merge_data(None, {"y": 2}) == {"y": 2}
