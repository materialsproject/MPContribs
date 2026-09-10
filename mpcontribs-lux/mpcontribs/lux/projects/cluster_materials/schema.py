"""Pydantic schema for contributed cluster and cited flat-band results."""

from __future__ import annotations

import re
from typing import Annotated, Literal

from emmet.core.mpid import MPID
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)
from pymatgen.core import Element


def _validate_compound_system(value: str) -> str:
    """Validate both element symbols while preserving the upload string."""
    symbols = value.split("-")
    if len(symbols) != 2:
        raise ValueError("compoundSystem must contain exactly two element symbols")

    try:
        for symbol in symbols:
            Element(symbol)
    except ValueError as exc:
        raise ValueError("compoundSystem contains an invalid element symbol") from exc

    return value


def _split_comma_separated(value: str, field_name: str) -> list[str]:
    """Return canonical comma-separated values or raise a validation error."""
    values = value.split(",")
    if any(not item or item != item.strip() for item in values):
        raise ValueError(
            f"{field_name} must contain nonempty values separated by commas "
            "without spaces"
        )
    return values


def _validate_lattice_dimensionalities(value: str) -> str:
    """Validate comma-separated flat-band lattice dimensionalities."""
    values = _split_comma_separated(value, "latticeDimensionalities")
    if any(item not in {"1", "2", "3"} for item in values):
        raise ValueError("latticeDimensionalities entries must be 1, 2, or 3")
    return value


def _validate_lattice_ids(value: str) -> str:
    """Validate comma-separated flat-band lattice identifiers."""
    values = _split_comma_separated(value, "latticeIds")
    if any(re.fullmatch(r"(?:LI|SK)-\d+", item) is None for item in values):
        raise ValueError("latticeIds entries must match LI-<digits> or SK-<digits>")
    return value


CompoundSystem = Annotated[
    str,
    StringConstraints(max_length=5),
    AfterValidator(_validate_compound_system),
]
CommaSeparatedDimensionalities = Annotated[
    str,
    StringConstraints(min_length=1, max_length=64),
    AfterValidator(_validate_lattice_dimensionalities),
]
CommaSeparatedLatticeIds = Annotated[
    str,
    StringConstraints(min_length=1, max_length=512),
    AfterValidator(_validate_lattice_ids),
]

_MODEL_CONFIG = ConfigDict(extra="forbid", allow_inf_nan=False)


class FlatBandProperties(BaseModel):
    """Selected flat-band model annotation from Neves et al. (2024)."""

    model_config = _MODEL_CONFIG

    sublatticeElement: Element = Field(
        description="Elemental sublattice hosting the selected flat-band model."
    )
    numberOfFlatBands: int = Field(
        ge=1,
        description="Number of flat bands hosted by the selected sublattice model.",
    )
    sitesInSublattice: int = Field(
        ge=1,
        description="Number of sites present in the selected flat-band model.",
    )
    latticeDimensionalities: CommaSeparatedDimensionalities = Field(
        description=(
            "Comma-separated integer dimensionalities, in latticeIds order, for "
            "the classified flat-band lattice motifs."
        ),
    )
    latticeIds: CommaSeparatedLatticeIds = Field(
        description=(
            "Comma-separated flat-band lattice identifiers assigned by Neves et "
            "al.; LI denotes lattice-invariant classification and SK denotes "
            "Systre-key classification."
        ),
    )
    remainsFlatWithDecay: bool = Field(
        description=(
            "Whether the selected model contains a flat band when hopping "
            "strength decays exponentially with bond length."
        )
    )

    @model_validator(mode="after")
    def validate_lattice_annotations(self) -> FlatBandProperties:
        """Require one dimensionality annotation for each lattice identifier."""
        if len(self.latticeDimensionalities.split(",")) != len(
            self.latticeIds.split(",")
        ):
            raise ValueError(
                "latticeDimensionalities and latticeIds must have equal lengths"
            )
        return self


class ClusterMaterial(BaseModel):
    """Main data fields for one Cluster Materials contribution."""

    model_config = _MODEL_CONFIG

    materialId: MPID = Field(
        description=(
            "Materials Project identifier used only as the external linkage key "
            "for this contribution."
        )
    )
    compoundSystem: CompoundSystem = Field(
        description=(
            "Transition-metal and anion pair used for the Cluster Finder search, "
            "formatted as <primary-transition-metal>-<anion>."
        )
    )
    numberOfClusters: int = Field(
        ge=1,
        description="Number of rows in this contribution's clusters table.",
    )
    clusterLatticeSpaceGroup: str = Field(
        min_length=1,
        max_length=32,
        description=(
            "Space-group symbol of the derived lattice whose sites are unique "
            "cluster centroids; this is not the parent material space group."
        ),
    )
    predictedDimensionality: Literal["0D", "1D", "2D", "3D"] = Field(
        description=(
            "Effective dimensionality assigned to the cluster-centroid lattice by "
            "the Cluster Finder classification."
        )
    )
    minimumAverageDistance: float = Field(
        gt=0,
        description=(
            "Minimum averageDistance, in angstroms, among the rows in this "
            "contribution's clusters table."
        ),
    )
    isPolar: bool = Field(
        description="Whether the parent material belongs to a polar crystal class."
    )
    isPiezoelectric: bool = Field(
        description=(
            "Whether the parent material's crystal class permits piezoelectricity."
        )
    )
    isEnantiomorphic: bool = Field(
        description=(
            "Whether the parent material belongs to an enantiomorphic space-group "
            "class."
        )
    )
    hasBatteryData: bool = Field(
        description=(
            "Whether this material appears in the reviewed Materials Project "
            "Battery Explorer snapshot. No battery properties are duplicated in "
            "this contribution."
        )
    )
    flatBand: FlatBandProperties | None = Field(
        default=None,
        description=(
            "Optional selected flat-band lattice annotation from Neves et al., "
            "npj Computational Materials 10, 39 (2024), "
            "doi:10.1038/s41524-024-01220-x."
        ),
    )
