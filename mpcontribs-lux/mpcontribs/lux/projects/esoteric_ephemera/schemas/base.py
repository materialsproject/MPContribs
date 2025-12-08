"""Define base schemas for machine learning interatomic potential data."""

from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field

from emmet.core.structure import StructureMetadata
from emmet.core.math import Matrix3D, Vector3D, Vector6D, matrix_3x3_to_voigt
from emmet.core.types.pymatgen_types.composition_adapter import CompositionType
from emmet.core.types.pymatgen_types.element_adapter import ElementType
from emmet.core.vasp.calc_types import RunType as VaspRunType

from pymatgen.core import Element, Structure

if TYPE_CHECKING:
    from typing_extensions import Self

    from emmet.core.tasks import TaskDoc


class MLTrainDoc(StructureMetadata, extra="allow"):  # type: ignore[call-arg]
    """Generic schema for ML training data."""

    cell: Matrix3D | None = Field(
        None,
        description="The 3x3 matrix of cell/lattice vectors, such that a is the first row, b the second, and c the third.",
    )

    atomic_numbers: list[int] | None = Field(
        None,
        description="The list of proton numbers at each site. Should be the same length as `cart_coords`",
    )

    cart_coords: list[Vector3D] | None = Field(
        None,
        description="The list of Cartesian coordinates of each atom. Should be the same length as `atomic_numbers`.",
    )

    magmoms: list[float] | None = Field(
        None, description="The list of on-site magnetic moments."
    )

    energy: float | None = Field(
        None, description="The total energy associated with this structure."
    )

    forces: list[Vector3D] | None = Field(
        None,
        description="The interatomic forces corresponding to each site in the structure.",
    )

    abs_forces: list[float] | None = Field(
        None, description="The magnitude of the interatomic force on each site."
    )

    stress: Vector6D | None = Field(
        None,
        description="The components of the symmetric stress tensor in Voigt notation (xx, yy, zz, yz, xz, xy).",
    )

    stress_matrix: Matrix3D | None = Field(
        None,
        description="The 3x3 stress tensor. Use this if the tensor is unphysically non-symmetric.",
    )

    bandgap: float | None = Field(None, description="The final DFT bandgap.")

    elements: list[ElementType] | None = Field(
        None,
        description="List of unique elements in the material sorted alphabetically.",
    )

    composition: CompositionType | None = Field(
        None, description="Full composition for the material."
    )

    composition_reduced: CompositionType | None = Field(
        None,
        title="Reduced Composition",
        description="Simplified representation of the composition.",
    )

    functional: VaspRunType | None = Field(
        None, description="The approximate functional used to generate this entry."
    )

    bader_charges: list[float] | None = Field(
        None, description="Bader charges on each site of the structure."
    )
    bader_magmoms: list[float] | None = Field(
        None,
        description="Bader on-site magnetic moments for each site of the structure.",
    )

    @cached_property
    def structure(self) -> Structure:
        """Get the structure associated with this entry."""
        site_props = {"magmom": self.magmoms} if self.magmoms else None
        return Structure(
            np.array(self.cell),
            [Element.from_Z(z) for z in self.atomic_numbers],  # type: ignore[union-attr]
            self.cart_coords,  # type: ignore[arg-type]
            coords_are_cartesian=True,
            site_properties=site_props,
        )

    @classmethod
    def from_structure(
        cls,
        meta_structure: Structure,
        fields: list[str] | None = None,
        **kwargs,
    ) -> Self:
        """
        Create an ML training document from an ordered structure and fields.

        This method mostly exists to ensure that the structure field is
        set because `meta_structure` does not populate it automatically.

        Parameters
        -----------
        meta_structure : Structure
            An ordered structure
        fields : list of str or None
            Additional fields in the document to populate
        **kwargs
            Any other fields / constructor kwargs
        """
        if not meta_structure.is_ordered:
            raise ValueError(
                f"{cls.__name__} only supports ordered structures at this time."
            )

        if (forces := kwargs.get("forces")) is not None and kwargs.get(
            "abs_forces"
        ) is None:
            kwargs["abs_forces"] = [np.linalg.norm(f) for f in forces]

        if magmoms := meta_structure.site_properties.get("magmom"):
            kwargs["magmoms"] = magmoms

        return super().from_structure(
            meta_structure=meta_structure,
            fields=fields,
            cell=meta_structure.lattice.matrix,
            atomic_numbers=[site.specie.Z for site in meta_structure],
            cart_coords=meta_structure.cart_coords,
            **kwargs,
        )

    @classmethod
    def from_task_doc(
        cls,
        task_doc: TaskDoc,
        **kwargs,
    ) -> list[Self]:
        """Create a list of ML training documents from the ionic steps in a TaskDoc.

        Parameters
        -----------
        task_doc : TaskDoc
        **kwargs
            Any kwargs to pass to `from_structure`.
        """
        entries = []

        for cr in task_doc.calcs_reversed[::-1]:
            nion = len(cr.output.ionic_steps)

            for iion, ionic_step in enumerate(cr.output.ionic_steps):
                structure = Structure.from_dict(ionic_step.structure.as_dict())
                # these are fields that should only be set on the final frame of a calculation
                # also patch in magmoms because of how Calculation works
                last_step_kwargs = {}
                if iion == nion - 1:
                    if magmom := cr.output.structure.site_properties.get("magmom"):
                        structure.add_site_property("magmom", magmom)
                    last_step_kwargs["bandgap"] = cr.output.bandgap
                    if bader_analysis := cr.bader:
                        for bk in (
                            "charge",
                            "magmom",
                        ):
                            last_step_kwargs[f"bader_{bk}s"] = bader_analysis[bk]

                if (_st := ionic_step.stress) is not None:
                    st = np.array(_st)
                    if np.allclose(st, st.T, rtol=1e-8):
                        # Stress tensor is symmetric
                        last_step_kwargs["stress"] = matrix_3x3_to_voigt(_st)
                    else:
                        # Stress tensor is non-symmetric
                        last_step_kwargs["stress_matrix"] = _st

                entries.append(
                    cls.from_structure(
                        meta_structure=structure,
                        energy=ionic_step.e_0_energy,
                        forces=ionic_step.forces,
                        functional=cr.run_type,
                        **last_step_kwargs,
                        **kwargs,
                    )
                )
        return entries

    @cached_property
    def to_ase_atoms(self):
        """Get the ASE Atoms associated with this entry."""

        try:
            from ase.calculators.singlepoint import SinglePointCalculator
            from ase import Atoms
        except ImportError:
            raise ImportError(
                "You must `pip install ase` to use the atoms functionality here!"
            )

        atoms = Atoms(
            positions=self.cart_coords,
            numbers=self.atomic_numbers,
            cell=self.cell,
        )
        calc = SinglePointCalculator(
            atoms,
            **{
                k: getattr(self, k, None)
                for k in {"energy", "forces", "stress", "magmoms"}
            },
        )
        atoms.calc = calc
        return atoms
