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
        # require_all_data_fields forces the full data-field set to be present.
        patch = StructurePatch(
            lattice=_lattice_payload(),
            sites=[_site_payload()],
            charge=0.0,
            cif="data_Fe2O3\n",
        )
        assert patch.lattice is not None
        assert patch.lattice.volume == 1.0

    def test_sites_is_a_list(self):
        # Regression: sites must be list[Site], not a single Site.
        patch = StructurePatch(
            lattice=_lattice_payload(),
            sites=[_site_payload()],
            charge=0.0,
            cif="data_Fe2O3\n",
        )
        assert isinstance(patch.sites, list)
        assert patch.sites[0].label == "Fe"


class TestStructurePatchRequireAllDataFields:
    """Coverage for the ``require_all_data_fields`` model validator.

    The data fields are {lattice, sites, charge, cif}. The rule: if any of them
    is set, all of them must be set. ``name`` is metadata and is exempt.
    """

    def _all_data_fields(self, **overrides) -> dict:
        payload = {
            "lattice": _lattice_payload(),
            "sites": [_site_payload()],
            "charge": 0.0,
            "cif": "data_Fe2O3\n",
        }
        payload.update(overrides)
        return payload

    # -- passing cases -------------------------------------------------------

    def test_empty_patch_passes(self):
        # No data fields set at all: nothing to enforce.
        assert StructurePatch().model_dump(exclude_unset=True) == {}

    def test_only_name_passes(self):
        # name is not a data field, so a name-only patch is allowed.
        patch = StructurePatch(name="renamed")
        assert patch.name == "renamed"

    def test_all_data_fields_set_passes(self):
        patch = StructurePatch(**self._all_data_fields())
        assert patch.lattice is not None
        assert patch.sites is not None
        assert patch.charge == 0.0
        assert patch.cif == "data_Fe2O3\n"

    def test_all_data_fields_plus_name_passes(self):
        patch = StructurePatch(**self._all_data_fields(name="renamed"))
        assert patch.name == "renamed"
        assert patch.cif == "data_Fe2O3\n"

    def test_all_data_fields_with_charge_zero_passes(self):
        # 0.0 is a legitimate, "set" value and must not be treated as absent.
        patch = StructurePatch(**self._all_data_fields(charge=0.0))
        assert patch.charge == 0.0

    # -- failing cases: exactly one field set --------------------------------

    @pytest.mark.parametrize(
        "field, value",
        [
            ("lattice", _lattice_payload()),
            ("sites", [_site_payload()]),
            ("charge", 1.0),
            ("cif", "data_Fe2O3\n"),
        ],
    )
    def test_single_data_field_raises(self, field, value):
        with pytest.raises(AppValidationError):
            StructurePatch(**{field: value})

    def test_single_data_field_with_name_raises(self):
        # name does not satisfy the "all data fields" requirement.
        with pytest.raises(AppValidationError):
            StructurePatch(name="renamed", charge=1.0)

    # -- failing cases: some but not all -------------------------------------

    def test_three_of_four_fields_raises(self):
        # Everything except charge -> still incomplete.
        payload = self._all_data_fields()
        del payload["charge"]
        with pytest.raises(AppValidationError):
            StructurePatch(**payload)

    def test_two_of_four_fields_raises(self):
        with pytest.raises(AppValidationError):
            StructurePatch(lattice=_lattice_payload(), cif="data_Fe2O3\n")

    def test_explicit_none_charge_counts_as_set(self):
        # Enforcement is by which fields were explicitly provided, not by value.
        # An explicit charge=None satisfies the requirement.
        patch = StructurePatch(
            lattice=_lattice_payload(),
            sites=[_site_payload()],
            cif="data_Fe2O3\n",
            charge=None,
        )
        assert patch.charge is None
        assert "charge" in patch.model_fields_set

    def test_omitted_charge_counts_as_unset(self):
        # Omitting charge entirely (three-of-four provided) is still rejected.
        with pytest.raises(AppValidationError):
            StructurePatch(
                lattice=_lattice_payload(),
                sites=[_site_payload()],
                cif="data_Fe2O3\n",
            )

    # -- failing cases: null non-nullable data fields ------------------------
    #
    # lattice, sites, and cif are required/non-null on the Structure document,
    # so patching them to None is rejected even when all four are provided.

    @pytest.mark.parametrize("field", ["lattice", "sites", "cif"])
    def test_null_non_nullable_field_raises(self, field):
        with pytest.raises(AppValidationError):
            StructurePatch(**self._all_data_fields(**{field: None}))

    def test_all_non_nullable_fields_null_raises(self):
        with pytest.raises(AppValidationError):
            StructurePatch(lattice=None, sites=None, charge=None, cif=None)

    def test_null_non_nullable_error_message(self):
        with pytest.raises(AppValidationError) as exc_info:
            StructurePatch(**self._all_data_fields(cif=None))
        assert "non-null" in exc_info.value.message

    # -- error content -------------------------------------------------------

    def test_error_message_and_context(self):
        with pytest.raises(AppValidationError) as exc_info:
            StructurePatch(charge=1.0)
        err = exc_info.value
        assert "lattice" in err.message
        assert err.status_code == 422
        assert err.error_code == "validation_error"
        # The offending model is attached as context for logging.
        assert "update" in err.context
        assert isinstance(err.context["update"], StructurePatch)


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
