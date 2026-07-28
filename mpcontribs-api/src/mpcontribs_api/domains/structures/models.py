from typing import Annotated

from beanie import PydanticObjectId
from pydantic import BaseModel, BeforeValidator, ConfigDict
from pymatgen.core import Element

from mpcontribs_api.domains._shared.filters import BaseFilter
from mpcontribs_api.domains._shared.models import Component, ComponentIn, DocumentOut
from mpcontribs_api.domains._shared.types import MD5Hash, NFKCStr
from mpcontribs_api.exceptions import ValidationError
from mpcontribs_api.projection import SparseFieldsModel


def _validate_lattice_matrix(value: object) -> list[list[float]]:
    """Validate a lattice matrix as exactly three rows of three numbers (row-major 3x3).

    A crystal lattice matrix is nine floats with a fixed shape, so it is stored and typed as a plain
    nested list.

    Args:
        value: the raw ``matrix`` payload from a request body or a stored document.

    Returns:
        list[list[float]]: the validated 3x3 matrix with every cell coerced to ``float``.

    Raises:
        ValidationError: if ``value`` is not a 3x3 nested sequence of numbers.
    """
    if not isinstance(value, (list, tuple)):
        raise ValidationError(f"lattice matrix must be a 3x3 nested list, got {type(value).__name__}")
    rows = list(value)
    if len(rows) != 3:
        raise ValidationError(f"lattice matrix must be 3x3: got {len(rows)} rows, expected 3")
    matrix: list[list[float]] = []
    for i, row in enumerate(rows):
        if not isinstance(row, (list, tuple)):
            raise ValidationError(f"lattice matrix row {i} must be a list of 3 numbers, got {type(row).__name__}")
        cells = list(row)
        if len(cells) != 3:
            raise ValidationError(f"lattice matrix must be 3x3: row {i} has {len(cells)} columns, expected 3")
        converted: list[float] = []
        for j, cell in enumerate(cells):
            # ``bool`` is an ``int`` subclass but is not a valid matrix entry.
            if isinstance(cell, bool) or not isinstance(cell, (int, float)):
                raise ValidationError(f"lattice matrix cell [{i}][{j}] must be numeric, got {cell!r}")
            converted.append(float(cell))
        matrix.append(converted)
    return matrix


# Row-major 3x3 matrix of floats; validated for shape, matching the stored (pymatgen) representation.
LatticeMatrix = Annotated[list[list[float]], BeforeValidator(_validate_lattice_matrix)]


class SiteProperties(BaseModel):
    magmom: float


class Species(BaseModel):
    element: Element
    occu: int


class Lattice(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    matrix: LatticeMatrix
    pbc: list[bool]
    a: float
    b: float
    c: float
    alpha: float
    beta: float
    gamma: float
    volume: float


class Site(BaseModel):
    species: list[Species]
    abc: list[float]
    properties: SiteProperties
    label: str
    xyz: list[float]


# Some things in Emmet-core that could assist in translating the pymatgen string to BaseModel
# In Mongo it is a single long string, but we could try to parse it into something typed
# It looks like it has some fields, then a table for n_atom_site_* with the subsequent lines being tab/space delimited
# rows
class Cif(BaseModel):
    pass


class Structure(Component):
    hash_fields = frozenset({"lattice", "sites", "charge"})
    lattice: Lattice
    sites: list[Site]
    charge: float | None
    cif: str  # Cif

    class Settings:
        name = "structures"


class StructureIn(ComponentIn):
    """User-supplied structure content."""

    lattice: Lattice
    sites: list[Site]
    charge: float | None = None
    cif: str


class StructureOut(DocumentOut[PydanticObjectId]):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str | None = None
    md5: MD5Hash | None = None
    lattice: Lattice | None = None
    sites: list[Site] | None = None
    charge: float | None = None
    cif: str | None = None

    @staticmethod
    def default_fields() -> tuple[str, ...]:
        return (
            "id",
            "name",
            "md5",
        )


class StructurePatch(SparseFieldsModel):
    name: str | None = None
    lattice: Lattice | None = None
    sites: list[Site] | None = None
    charge: float | None = None
    cif: str | None = None


class StructureFilter(BaseFilter):
    id: PydanticObjectId | None = None
    id__in: list[PydanticObjectId] | None = None
    id__neq: PydanticObjectId | None = None

    md5: MD5Hash | None = None
    md5__in: list[MD5Hash] | None = None
    md5__neq: MD5Hash | None = None

    name: NFKCStr | None = None
    name__in: list[NFKCStr] | None = None
    name__neq: NFKCStr | None = None
    name__ilike: NFKCStr | None = None

    # sites

    # sorting
    order_by: list[str] | None = None

    class Constants(BaseFilter.Constants):
        model = Structure
