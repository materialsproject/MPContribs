import pytest

from mpcontribs_api.domains.structures.models import Structure, StructureIn

pytestmark = [pytest.mark.db, pytest.mark.asyncio(loop_scope="session")]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# A deliberately asymmetric matrix so a transposed or reordered round-trip would be caught.
MATRIX = [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0], [7.0, 8.0, 9.0]]


def _structure_in(**overrides) -> StructureIn:
    payload = {
        "name": "Fe2O3",
        "lattice": {
            "matrix": MATRIX,
            "pbc": [True, True, True],
            "a": 1.0,
            "b": 1.0,
            "c": 1.0,
            "alpha": 90.0,
            "beta": 90.0,
            "gamma": 90.0,
            "volume": 1.0,
        },
        "sites": [
            {
                "species": [{"element": "Fe", "occu": 1}],
                "abc": [0.0, 0.0, 0.0],
                "properties": {"magmom": 2.2},
                "label": "Fe",
                "xyz": [0.0, 0.0, 0.0],
            }
        ],
        "charge": 0.0,
        "cif": "data_Fe2O3\n_cell_length_a 1.0\n",
    }
    payload.update(overrides)
    return StructureIn(**payload)


# ---------------------------------------------------------------------------
# Lattice matrix round-trip through MongoDB
#
# Regression: Lattice.matrix used to be typed as a PolarsFrame whose BSON form
# (a bare column list) could not be read back by _coerce_frame. Retyped as a
# plain row-major 3x3 nested list, it now survives an insert -> read cycle with
# values and ordering intact.
# ---------------------------------------------------------------------------


class TestLatticeMatrixRoundTrip:
    async def test_matrix_survives_insert_and_read(self, db):
        doc = Structure.from_input(_structure_in())
        await doc.insert()

        read = await Structure.get(doc.id)
        assert read is not None
        assert read.lattice.matrix == MATRIX

    async def test_matrix_ordering_preserved(self, db):
        doc = Structure.from_input(_structure_in())
        await doc.insert()

        read = await Structure.get(doc.id)
        assert read is not None
        # Row-major: element [i][j] lands back exactly where it started.
        for i in range(3):
            for j in range(3):
                assert read.lattice.matrix[i][j] == MATRIX[i][j]

    async def test_matrix_cells_are_floats_after_read(self, db):
        doc = Structure.from_input(_structure_in())
        await doc.insert()

        read = await Structure.get(doc.id)
        assert read is not None
        assert all(isinstance(cell, float) for row in read.lattice.matrix for cell in row)
