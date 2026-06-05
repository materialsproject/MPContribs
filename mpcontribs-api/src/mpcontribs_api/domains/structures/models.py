import polars as pl
from beanie import PydanticObjectId
from fastapi_filter.contrib.beanie import Filter
from pydantic import BaseModel, ConfigDict, field_serializer, field_validator
from pymatgen.core import Element

from mpcontribs_api.domains._shared.models import BaseDocumentWithInput
from mpcontribs_api.types import MD5Hash


class SiteProperties(BaseModel):
    magmom: float


class Species(BaseModel):
    element: Element
    occu: int


class Lattice(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    matrix: pl.DataFrame
    pbc: list[bool]
    a: float
    b: float
    c: float
    alpha: float
    beta: float
    gamma: float
    volume: float

    @field_validator("matrix", mode="before")
    @classmethod
    def coerce_matrix(cls, v: object) -> pl.DataFrame:
        if isinstance(v, pl.DataFrame):
            return v
        if isinstance(v, dict):
            return pl.DataFrame(v)
        # MongoDB returns rows as a list of lists
        if isinstance(v, list):
            return pl.DataFrame(v)
        raise ValueError(f"cannot coerce {type(v)} to pl.DataFrame")

    @field_serializer("matrix")
    def serialize_matrix(self, matrix: pl.DataFrame) -> dict:
        return matrix.to_dict(as_series=False)


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


class Structure(BaseDocumentWithInput[PydanticObjectId]):
    name: str
    md5: MD5Hash
    lattice: Lattice
    sites: list[Site]
    charge: float | None
    cif: str  # Cif

    class Settings:
        name = "structures"


class StructureIn(Structure):
    pass


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
