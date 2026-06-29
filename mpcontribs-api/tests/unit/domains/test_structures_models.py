import polars as pl
import pytest
from beanie import PydanticObjectId
from pydantic import ValidationError as PydanticValidationError
from pymatgen.core import Element

from mpcontribs_api.domains.structures.models import (
    Lattice,
    SiteProperties,
    Species,
    Structure,
    StructureFilter,
    StructureIn,
    StructureOut,
    StructurePatch,
)
from mpcontribs_api.exceptions import ValidationError as AppValidationError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _lattice_payload(**overrides) -> dict:
    payload = {
        "matrix": {"x": [1.0, 0.0, 0.0], "y": [0.0, 1.0, 0.0], "z": [0.0, 0.0, 1.0]},
        "pbc": [True, True, True],
        "a": 1.0,
        "b": 1.0,
        "c": 1.0,
        "alpha": 90.0,
        "beta": 90.0,
        "gamma": 90.0,
        "volume": 1.0,
    }
    payload.update(overrides)
    return payload


def _site_payload(**overrides) -> dict:
    payload = {
        "species": [{"element": "Fe", "occu": 1}],
        "abc": [0.0, 0.0, 0.0],
        "properties": {"magmom": 2.2},
        "label": "Fe",
        "xyz": [0.0, 0.0, 0.0],
    }
    payload.update(overrides)
    return payload


def _structure_payload(**overrides) -> dict:
    payload = {
        "_id": PydanticObjectId(),
        "name": "Fe2O3",
        "md5": "f" * 32,
        "lattice": _lattice_payload(),
        "sites": [_site_payload()],
        "charge": 0.0,
        "cif": "data_Fe2O3\n_cell_length_a 1.0\n",
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Leaf models
# ---------------------------------------------------------------------------


class TestSiteProperties:
    def test_valid(self):
        assert SiteProperties(magmom=1.5).magmom == 1.5

    def test_missing_magmom_raises(self):
        with pytest.raises(PydanticValidationError):
            SiteProperties()


class TestSpecies:
    def test_element_coerced_from_symbol(self):
        species = Species(element="Fe", occu=1)
        assert species.element is Element.Fe
        assert species.occu == 1

    def test_invalid_symbol_raises(self):
        with pytest.raises(PydanticValidationError):
            Species(element="Xx", occu=1)

    def test_element_enum_passthrough(self):
        assert Species(element=Element.O, occu=2).element is Element.O


class TestLattice:
    def test_valid_construction(self):
        lattice = Lattice(**_lattice_payload())
        assert isinstance(lattice.matrix, pl.DataFrame)
        assert lattice.pbc == [True, True, True]
        assert lattice.volume == 1.0

    def test_matrix_coerced_from_dict(self):
        lattice = Lattice(**_lattice_payload())
        assert lattice.matrix.columns == ["x", "y", "z"]

    def test_missing_angles_raise(self):
        payload = _lattice_payload()
        del payload["alpha"]
        with pytest.raises(PydanticValidationError):
            Lattice(**payload)


# ---------------------------------------------------------------------------
# Structure / StructureIn
# ---------------------------------------------------------------------------


class TestStructure:
    def test_valid_construction(self):
        structure = Structure(**_structure_payload())
        assert structure.name == "Fe2O3"
        assert len(structure.sites) == 1
        assert structure.sites[0].species[0].element is Element.Fe

    def test_collection_name(self):
        assert Structure.Settings.name == "structures"

    def test_charge_is_required_but_nullable(self):
        assert Structure(**_structure_payload(charge=None)).charge is None
        payload = _structure_payload()
        del payload["charge"]
        with pytest.raises(PydanticValidationError):
            Structure(**payload)

    def test_md5_is_computed_not_taken_from_input(self):
        # A client-supplied md5 is overwritten by the content-derived hash.
        structure = Structure(**_structure_payload(md5="a" * 32))
        assert structure.md5 != "a" * 32
        assert len(structure.md5) == 32

    def test_same_content_same_md5(self):
        assert Structure(**_structure_payload()).md5 == Structure(**_structure_payload()).md5

    def test_different_charge_different_md5(self):
        assert Structure(**_structure_payload(charge=0.0)).md5 != Structure(**_structure_payload(charge=1.0)).md5

    def test_cif_kept_as_raw_string(self):
        structure = Structure(**_structure_payload())
        assert structure.cif.startswith("data_Fe2O3")

    def test_structure_in_has_no_id_or_md5(self):
        assert "md5" not in StructureIn.model_fields
        assert "id" not in StructureIn.model_fields

    def test_from_input_assigns_id_and_computes_md5(self):
        sin = StructureIn(
            name="Fe2O3",
            lattice=_lattice_payload(),
            sites=[_site_payload()],
            charge=0.0,
            cif="data_Fe2O3\n",
        )
        doc = Structure.from_input(sin)
        assert isinstance(doc, Structure)
        assert doc.id is not None
        assert len(doc.md5) == 32


# ---------------------------------------------------------------------------
# StructureOut
# ---------------------------------------------------------------------------


class TestStructureOut:
    def test_all_fields_optional(self):
        out = StructureOut()
        assert out.id is None
        assert out.name is None
        assert out.md5 is None

    def test_default_fields(self):
        assert StructureOut.default_fields() == ["id", "name", "md5"]

    def test_default_fields_parseable(self):
        # The route default must survive parse_fields without raising.
        parsed = StructureOut.parse_fields(StructureOut.default_fields())
        assert parsed == frozenset({"id", "name", "md5"})

    def test_populates_id_from_mongo_alias(self):
        oid = PydanticObjectId()
        assert StructureOut.model_validate({"_id": oid}).id == oid


# ---------------------------------------------------------------------------
# StructurePatch
# ---------------------------------------------------------------------------


class TestStructurePatch:
    def test_all_fields_optional(self):
        patch = StructurePatch()
        assert patch.name is None
        assert patch.lattice is None
        assert patch.sites is None

    def test_partial_patch_excludes_unset(self):
        patch = StructurePatch(name="renamed")
        assert patch.model_dump(exclude_unset=True) == {"name": "renamed"}

    def test_lattice_patchable(self):
        patch = StructurePatch(lattice=_lattice_payload())
        assert patch.lattice is not None
        assert patch.lattice.volume == 1.0

    def test_sites_is_a_list(self):
        # Regression: sites must be list[Site], not a single Site.
        patch = StructurePatch(sites=[_site_payload()])
        assert isinstance(patch.sites, list)
        assert patch.sites[0].label == "Fe"


# ---------------------------------------------------------------------------
# StructureFilter
# ---------------------------------------------------------------------------


class TestStructureFilter:
    def test_empty_filter(self):
        filter = StructureFilter()
        assert filter.id is None
        assert filter.name__ilike is None

    def test_constants_bind_structure_model(self):
        assert StructureFilter.Constants.model is Structure

    def test_md5_value_validated(self):
        assert StructureFilter(md5="A" * 32).md5 == "a" * 32

    def test_invalid_md5_raises(self):
        with pytest.raises(AppValidationError):
            StructureFilter(md5="short")
