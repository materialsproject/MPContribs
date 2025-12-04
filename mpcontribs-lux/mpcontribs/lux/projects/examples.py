"""Define example schemas for users.

This schema is used for the public MPContribs project `test_solid_data`:
    https://next-gen.materialsproject.org/contribs/projects/test_solid_data
You can find its download on AWS S3:
    https://materialsproject-contribs.s3.amazonaws.com/index.html#test_solid_data/solid_data.parquet
"""

from functools import cached_property

from pydantic import BaseModel, Field

from pymatgen.core import Structure

class ExampleSchema(BaseModel):
    """Define example schema with appropriate levels of annotated metadata."""

    formula : str | None = Field(
        None, description = "The chemical formula of the unit cell."
    )

    a0 : float | None = Field(
        None, description = "The experimental equilibrium cubic "
        "lattice constant a, in Å,  including zero-point corrections "
        "for nuclear vibration."
    )

    b0 : float | None = Field(
        None, description = "The experimental bulk modulus at "
        "optimal lattice geometry, in GPa, including zero-point "
        "corrections for nuclear vibration."
    )

    e0 : float | None = Field(
        None, description = "The experimental cohesive energy, in eV/atom, "
        "including zero-point corrections for nuclear vibration."
    )

    cif : str | None = Field(
        None, description="The structure represented as a Crystallographic Information File."
    )

    material_id : str | None = Field(
        None, description = "The Materials Project ID of the structure which "
        "corresponds to this entry. The ID will start with `mp-`"
    )

    @cached_property
    def get_pymatgen_structure(self) -> Structure | None:
        """Get the pymatgen structure for this entry, if it exists.
        
        Example of adding functionality to downstream users to interact 
        with your data.
        
        You can provide more advanced analysis tools, which we also show below.
        """
        if self.cif:
            return Structure.from_str(self.cif,fmt="cif")
        return None