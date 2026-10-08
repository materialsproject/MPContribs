"""Top-level schema: the contribution data for one relaxed MXene structure.

`MXeneEntry` is exactly the `data` of one MPContribs contribution. Every
field is a scalar or a short validated string; units are given in each
field's `json_schema_extra`. The relaxed structure is submitted alongside, in
the contribution's `structures` component.
"""

from __future__ import annotations

from mpcontribs.lux.projects.two_d_mxenes.schemas.descriptors import (
    StructureDescriptors,
)
from mpcontribs.lux.projects.two_d_mxenes.schemas.labels import MXeneLabel
from mpcontribs.lux.projects.two_d_mxenes.schemas.properties import MXeneProperties
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pymatgen.core import Composition

MXENE_ID_PATTERN = (
    r"^[A-Z][a-z]?[2-4][CN][2-3]?(?:[FO]2)?-(?:h1a|h1b|h2|h|t)(?:-[12])?$"
)
"""`<formula>-<label>`, e.g. `Ti3C2O2-h1a-2` or `Mo2C-t`."""


def _split(sequence: str) -> list[str]:
    return sequence.split("-")


class MXeneEntry(BaseModel):
    """Contribution data for one MXene: labels, descriptors and properties.

    On construction the labels are checked against the descriptors measured
    from the structure: the formula and layer sequence must match the labels,
    the core coordination sequence must match the stacking, and the
    outer-metal coordination must match the termination site on both surfaces.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    mxeneId: str = Field(
        max_length=20,
        pattern=MXENE_ID_PATTERN,
        description="Unique identifier within this project: formula plus "
        "folder label, e.g. `Hf2CF2-h-1` or `Ti3C2-h1a`.",
    )
    labels: MXeneLabel = Field(
        description="Chemistry and stacking labels of this MXene."
    )
    descriptors: StructureDescriptors = Field(
        description="Geometric descriptors computed from the relaxed structure."
    )
    properties: MXeneProperties | None = Field(
        None, description="Computed properties: energetics and elastic constants."
    )

    @model_validator(mode="after")
    def _check_labels_against_descriptors(self) -> MXeneEntry:
        labels, desc = self.labels, self.descriptors

        expected_id = f"{labels.formula}-{labels.label}"
        if self.mxeneId != expected_id:
            raise ValueError(f"mxeneId must be {expected_id!r}, got {self.mxeneId!r}")

        expected = Composition(labels.formula).reduced_composition
        actual = Composition(desc.reducedFormula).reduced_composition
        if not expected.almost_equals(actual):
            raise ValueError(
                f"Labels imply {labels.formula} but the structure is "
                f"{desc.reducedFormula}"
            )

        if desc.layerSequence != labels.layer_sequence:
            raise ValueError(
                f"Labels imply layers {labels.layer_sequence} but the structure "
                f"has {desc.layerSequence}"
            )

        measured = _split(desc.coordinationSequence)
        implied = _split(labels.coordination_sequence)
        core_measured = measured[1:-1] if labels.termination else measured
        core_implied = implied[1:-1] if labels.termination else implied
        if core_measured != core_implied:
            raise ValueError(
                f"Stacking {labels.stacking!r} implies core coordination "
                f"{'-'.join(core_implied)} but the structure has "
                f"{'-'.join(core_measured)}"
            )

        if labels.termination and (measured[0], measured[-1]) != (
            implied[0],
            implied[-1],
        ):
            raise ValueError(
                f"Termination site {labels.terminationSite} of "
                f"{labels.stacking!r} (n={labels.n}) implies outer-metal "
                f"coordination {implied[0]} on both surfaces but the structure "
                f"has {(measured[0], measured[-1])}"
            )
        return self
