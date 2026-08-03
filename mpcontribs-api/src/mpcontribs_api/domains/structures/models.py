from typing import Self

from beanie import PydanticObjectId
from pydantic import BaseModel, ConfigDict, model_validator
from pymatgen.core import Element

from mpcontribs_api.domains._shared.filters import BaseFilter
from mpcontribs_api.domains._shared.models import Component, ComponentIn, DocumentOut
from mpcontribs_api.domains._shared.types import MD5Hash, PolarsFrame
from mpcontribs_api.exceptions import ValidationError
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
    def default_fields() -> list[str]:
        return [
            "id",
            "name",
            "md5",
        ]


class StructurePatch(SparseFieldsModel):
    name: str | None = None
    lattice: Lattice | None = None
    sites: list[Site] | None = None
    charge: float | None = None
    cif: str | None = None

    @model_validator(mode="after")
    def require_all_data_fields(self) -> Self:
        """If any of {lattice, sites, charge, cif} are being updated, all must be specified.

        charge is nullable; lattice, sites, and cif must be non-null when patched.
        """
        data_fields = frozenset({"lattice", "sites", "charge", "cif"})
        set_fields = data_fields & self.model_fields_set
        if set_fields and set_fields != data_fields:
            raise ValidationError("must specify all {lattice, sites, charge, cif} if updating one.", update=self)
        if set_fields and (self.lattice is None or self.sites is None or self.cif is None):
            raise ValidationError("lattice, sites, and cif must be non-null.", update=self)
        return self


class StructureFilter(BaseFilter):
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

    # sorting
    order_by: list[str] | None = None

    class Constants(BaseFilter.Constants):
        model = Structure
