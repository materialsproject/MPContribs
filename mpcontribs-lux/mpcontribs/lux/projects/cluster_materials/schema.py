"""Pydantic schema for contributed cluster and cited flat-band results."""

from __future__ import annotations

from collections import Counter
import re
from math import isclose
from typing import Annotated, Literal

import pandas as pd
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)
from pymatgen.core import Element

from .cluster import Cluster
from .cluster_membership import (
    ClusterMembership,
    group_memberships,
)
from .cluster_point_group import ClusterPointGroup


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


CoreStructureId = Annotated[
    str, StringConstraints(pattern=r"^mp-(?:[0-9]{1,12}|[a-z]{1,16})$")
]
HighlightingReason = Literal[
    "missing_summary_structure",
    "unresolved_geometry",
    "cluster_count_mismatch",
    "cluster_sizes_mismatch",
    "cluster_compositions_mismatch",
    "cluster_distances_mismatch",
    "cluster_point_groups_mismatch",
    "processing_error",
    "core_origin_missing",
    "core_structure_unavailable",
    "core_structure_mismatch",
    "core_origin_ambiguous",
]


class ClusterMaterial(BaseModel):
    """Main data fields for one Cluster Materials contribution."""

    model_config = _MODEL_CONFIG

    coreStructureId: CoreStructureId | None = Field(
        default=None,
        description=(
            "Exact structure-origin task_id, saved once from Core and retrieved through materials.tasks. "
            "Requires the mp- prefix for numeric and encoded task IDs. This is not the changing material identifier."
        ),
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

    highlightingUnavailableReason: HighlightingReason | None = Field(
        default=None,
        description="Optional reason that clusterMemberships is unavailable. Table presence determines availability.",
    )


def validate_material(
    cluster_material: ClusterMaterial,
    clusters: pd.DataFrame,
    cluster_groups: pd.DataFrame,
    cluster_memberships: pd.DataFrame | None = None,
) -> bool:
    """Validate main data, both original tables, and optional viewer membership table."""
    cluster_rows = [
        Cluster.model_validate(row) for row in clusters.to_dict(orient="records")
    ]
    cluster_group_rows = [
        ClusterPointGroup.model_validate(row)
        for row in cluster_groups.to_dict(orient="records")
    ]

    if len(cluster_rows) != cluster_material.numberOfClusters:
        raise ValueError("numberOfClusters must equal the number of clusters rows")
    cluster_material_ids = {str(row.materialId) for row in cluster_rows}
    if len(cluster_material_ids) != 1:
        raise ValueError("clusters must contain exactly one materialId")
    if not isclose(
        min(row.averageDistance for row in cluster_rows),
        cluster_material.minimumAverageDistance,
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

    expected = [row.symbol for row in cluster_group_rows]
    for row in cluster_rows:
        if row.symbol is not None and row.symbol not in expected:
            raise ValueError("Cluster symbol must exist in clusterPointGroups")
    has_members = cluster_memberships is not None and not cluster_memberships.empty
    if not has_members:
        return True  # Legacy and explicitly unavailable contributions remain valid.
    if cluster_material.coreStructureId is None:
        raise ValueError("Memberships require coreStructureId")
    if cluster_material.highlightingUnavailableReason is not None:
        raise ValueError("Memberships cannot accompany an unavailable reason")
    rows = [
        ClusterMembership.model_validate(row)
        for row in cluster_memberships.to_dict(orient="records")
    ]
    member_groups = group_memberships(rows)
    if len(member_groups) != len(cluster_rows):
        raise ValueError("Memberships must cover every source cluster exactly once")
    if {str(row.materialId) for row in rows} != cluster_material_ids:
        raise ValueError("Membership materialId must match the source tables")
    observed = []
    for members, cluster in zip(member_groups, cluster_rows):
        if len(members) != cluster.size:
            raise ValueError("Membership size must match its clusters row")
        if cluster.symbol is None:
            raise ValueError("Every cluster with memberships requires a symbol")
        observed.append(cluster.symbol)
    if set(observed) != set(expected) or Counter(expected) - Counter(observed):
        raise ValueError("Cluster symbols must cover the source point groups")
    return True
