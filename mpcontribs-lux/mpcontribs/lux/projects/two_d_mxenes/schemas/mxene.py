"""Top-level schema: one record per relaxed MXene structure.

Data are from:
    N. Oyeniran et al., "A Panoramic View of MXenes via a New Design Strategy",
    Adv. Funct. Mater. (2025), https://doi.org/10.1002/adfm.202508047
    (preprint: https://doi.org/10.48550/arXiv.2501.15390).
"""

from __future__ import annotations

from mpcontribs.lux.projects.two_d_mxenes.schemas.labels import MXeneLabel
from mpcontribs.lux.projects.two_d_mxenes.schemas.properties import MXeneProperties
from mpcontribs.lux.projects.two_d_mxenes.schemas.structure import (
    MXeneStructure,
    StructureDescriptors,
)
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pymatgen.core import Composition, Structure

_MODEL_CONFIG = ConfigDict(extra="forbid", allow_inf_nan=False)


def infer_chemistry(composition: Composition) -> dict:
    """Infer M, X, T and n from the composition of an M_{n+1}X_nT_x slab.

    Returns
    -----------
    dict with keys `metal`, `nonmetal`, `termination` (None if pristine), `n`
    """
    metals = [el.symbol for el in composition if el.is_transition_metal]
    nonmetals = [el.symbol for el in composition if el.symbol in {"C", "N"}]
    terms = [el.symbol for el in composition if el.symbol in {"F", "O"}]
    if len(metals) != 1 or len(nonmetals) != 1 or len(terms) > 1:
        raise ValueError(f"Cannot infer MXene labels from {composition.formula}")
    n_units = composition[metals[0]] - composition[nonmetals[0]]
    if n_units <= 0:
        raise ValueError(f"Not an M_(n+1)X_n composition: {composition.formula}")
    return {
        "metal": metals[0],
        "nonmetal": nonmetals[0],
        "termination": terms[0] if terms else None,
        "n": round(composition[nonmetals[0]] / n_units),
    }


class MXeneEntry(BaseModel):
    """A single MXene: its labels, relaxed structure and properties.

    On construction the labels are checked against the structure: the
    composition must be M_{n+1}X_nT_x with the labelled elements and n, and
    the coordination sequence measured from the structure must match the
    stacking label and termination site.
    """

    model_config = _MODEL_CONFIG

    mxeneId: str = Field(
        description="Unique identifier within this project: formula plus "
        "dataset label, e.g. `Hf2CF2-h-1` or `Ti3C2-h1a`.",
    )
    labels: MXeneLabel = Field(
        description="Chemistry and stacking labels of this MXene."
    )
    structure: MXeneStructure = Field(
        description="Relaxed slab structure (from the dataset's CONTCAR)."
    )
    descriptors: StructureDescriptors = Field(
        description="Geometric descriptors computed from `structure`."
    )
    properties: MXeneProperties | None = Field(
        None, description="Computed properties from the authors' spreadsheet."
    )

    @classmethod
    def from_structure(
        cls,
        structure: Structure,
        stacking: str,
        terminationSite: int | None = None,
        properties: MXeneProperties | None = None,
    ) -> MXeneEntry:
        """Build an entry, inferring M, X, T and n from the composition.

        Parameters
        -----------
        structure : Structure
            Relaxed slab structure.
        stacking : str
            Stacking label, e.g. `h1a`.
        terminationSite : int or None
            Termination site (1 or 2), or None for a pristine MXene.
        properties : MXeneProperties or None
            Properties from the authors' spreadsheet, if available.
        """
        labels = MXeneLabel(
            **infer_chemistry(structure.composition),
            stacking=stacking,
            terminationSite=terminationSite,
        )
        return cls(
            mxeneId=f"{labels.formula}-{labels.label}",
            labels=labels,
            structure=MXeneStructure.from_structure(structure),
            descriptors=StructureDescriptors.from_structure(structure),
            properties=properties,
        )

    @model_validator(mode="after")
    def _check_labels_against_structure(self) -> MXeneEntry:
        expected = Composition(self.labels.formula).reduced_composition
        actual = Composition(
            {el: self.structure.species.count(el) for el in set(self.structure.species)}
        ).reduced_composition
        if not expected.almost_equals(actual):
            raise ValueError(
                f"Labels imply {expected.reduced_formula} but the structure "
                f"is {actual.reduced_formula}"
            )

        if self.core_sequence != self.labels.core_sequence:
            raise ValueError(
                f"Stacking {self.labels.stacking!r} implies core coordination "
                f"{'-'.join(self.labels.core_sequence)} but the structure has "
                f"{'-'.join(self.core_sequence)}"
            )

        if self.labels.terminationSite is not None:
            coord = self.labels.termination_coordination
            if self.termination_coordination != (coord, coord):
                raise ValueError(
                    f"Termination site {self.labels.terminationSite} of "
                    f"{self.labels.stacking!r} (n={self.labels.n}) implies "
                    f"outer-metal coordination {coord} on both surfaces but the "
                    f"structure has {self.termination_coordination}"
                )
        return self

    @property
    def core_sequence(self) -> list[str]:
        """Measured coordination of the layers between the outer metal layers."""
        seq = self.descriptors.coordinationSequence
        return seq[1:-1] if self.labels.termination else seq

    @property
    def termination_coordination(self) -> tuple[str, str] | None:
        """Measured coordination of the bottom and top outer metal layers.

        This is set by the termination site: `O` if the termination sits
        staggered with respect to the X layer beneath the outer metal, `P` if
        it sits directly above an X atom. None for pristine MXenes.
        """
        if not self.labels.termination:
            return None
        seq = self.descriptors.coordinationSequence
        return seq[0], seq[-1]
