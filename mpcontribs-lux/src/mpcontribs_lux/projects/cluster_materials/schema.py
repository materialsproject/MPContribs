"""Pydantic schema for contributed cluster and cited flat-band results."""

from __future__ import annotations

import re
from math import isclose
from typing import Annotated, ClassVar, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)
from pymatgen.core import Element, Structure

from mpcontribs_lux.registry import LuxRegistry, SchemaType, ValidatedTables

from .cluster import Cluster
from .cluster_point_group import ClusterPointGroup


def _validate_compound_system(value: str) -> str:
    """Validate both element symbols while preserving the upload string."""
    symbols = value.split("-")
    if len(symbols) != 2:
        raise ValueError("compoundSystem must contain exactly two element symbols")

    try:
        for symbol in symbols:
            _ = Element(symbol)
    except ValueError as exc:
        raise ValueError("compoundSystem contains an invalid element symbol") from exc

    return value


def _validate_lattice_dimensionalities(value: str) -> str:
    """Validate comma-separated flat-band lattice dimensionalities."""
    values = [item.strip() for item in value.split(",")]
    if any(item not in {"1", "2", "3"} for item in values):
        raise ValueError("latticeDimensionalities entries must be 1, 2, or 3")
    return ",".join(values)


def _validate_lattice_ids(value: str) -> str:
    """Validate comma-separated flat-band lattice identifiers."""
    values = [item.strip() for item in value.split(",")]
    if any(re.fullmatch(r"(?:LI|SK)-\d+", item) is None for item in values):
        raise ValueError("latticeIds entries must match LI-<digits> or SK-<digits>")
    return ",".join(values)


CompoundSystem = Annotated[
    str,
    StringConstraints(max_length=5),
    AfterValidator(_validate_compound_system),
]
CommaSeparatedDimensionalities = Annotated[
    str,
    StringConstraints(min_length=1, max_length=512),
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

    model_config: ClassVar[ConfigDict] = _MODEL_CONFIG

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


@LuxRegistry.register_schema(
    project_name="cluster_materials", schema_type=SchemaType.contribution
)
class ClusterMaterial(BaseModel):
    """Main data fields for one Cluster Materials contribution."""

    model_config: ClassVar[ConfigDict] = _MODEL_CONFIG

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


@LuxRegistry.register_validator("cluster_materials", contribution=ClusterMaterial)
def validate_material(
    contribution: ClusterMaterial,
    tables: ValidatedTables,
    _structures: dict[str, Structure] | None = None,
) -> None:
    """Return True when main data and both tables satisfy shared invariants.

    This validator expects ``Cluster`` and ``ClusterPointGroup`` entries.
    """
    try:
        cluster_rows = tables.rows(Cluster)
        cluster_group_rows = tables.rows(ClusterPointGroup)
    except KeyError as err:
        raise ValueError(f"cluster_materials requires a {err.args[0]!r} table") from err

    if len(cluster_rows) != contribution.numberOfClusters:
        raise ValueError("numberOfClusters must equal the number of clusters rows")
    cluster_material_ids = {str(row.materialId) for row in cluster_rows}
    if len(cluster_material_ids) != 1:
        raise ValueError("clusters must contain exactly one materialId")
    if not isclose(
        min(row.averageDistance for row in cluster_rows),
        contribution.minimumAverageDistance,
        rel_tol=1e-9,
        abs_tol=1e-6,
    ):
        raise ValueError(
            "minimumAverageDistance must equal the minimum clusters-table distance"
        )
    if not cluster_group_rows:
        raise ValueError("clusterPointGroups must contain at least one row")
    if len(cluster_group_rows) > len(cluster_rows):
        raise ValueError(
            "clusterPointGroups cannot contain more rows than the clusters table"
        )
    group_material_ids = {str(row.materialId) for row in cluster_group_rows}
    if len(group_material_ids) != 1:
        raise ValueError("clusterPointGroups must contain exactly one materialId")
    if cluster_material_ids != group_material_ids:
        raise ValueError("clusters and clusterPointGroups materialId values must match")
    labels = [row.label for row in cluster_group_rows]
    if len(labels) != len(set(labels)):
        raise ValueError("clusterPointGroups labels must be unique")
