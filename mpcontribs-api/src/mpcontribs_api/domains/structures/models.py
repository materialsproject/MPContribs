from beanie import PydanticObjectId
from fastapi_filter.contrib.beanie import Filter
from pydantic import BaseModel, ConfigDict
from pymatgen.core import Element

from mpcontribs_api.domains._shared.models import Component, DocumentOut
from mpcontribs_api.domains._shared.types import MD5Hash, PolarsFrame
from mpcontribs_api.projection import SparseFieldsModel


class SiteProperties(BaseModel):
    magmom: float


class Species(BaseModel):
    element: Element
    occu: int


class Lattice(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    matrix: PolarsFrame
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


class StructureIn(Structure):
    pass


class StructureOut(DocumentOut[PydanticObjectId]):
    name: str | None = None
    md5: MD5Hash | None = None

    @staticmethod
    def default_fields() -> list[str]:
        return [
            "id",
            "name",
            "md5",
        ]


class StructurePatch(SparseFieldsModel):
    name: str | None = None
    lattice: Lattice | None = None
    sites: Site | None = None


class StructureFilter(Filter):
    id: PydanticObjectId | None = None
    id__in: list[PydanticObjectId] | None = None
    id__neq: PydanticObjectId | None = None

    md5: MD5Hash | None = None
    md5__in: list[MD5Hash] | None = None
    md5__neq: MD5Hash | None = None

    name: str | None = None
    name__in: list[str] | None = None
    name__neq: str | None = None
    name__ilike: str | None = None

    # sites

    class Constants(Filter.Constants):
        model = Structure
