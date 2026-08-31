"""Pydantic schemas for contributed cluster and cited flat-band results."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


ElementSymbol = Annotated[
    str,
    StringConstraints(pattern=r"^[A-Z][a-z]?$"),
]
MaterialId = Annotated[
    str,
    StringConstraints(pattern=r"^mp-\d+$"),
]
CompoundSystem = Annotated[
    str,
    StringConstraints(pattern=r"^[A-Z][a-z]?-[A-Z][a-z]?$"),
]
ClusterLabel = Annotated[
    str,
    StringConstraints(pattern=r"^X\d+$"),
]
FlatBandLatticeId = Annotated[
    str,
    StringConstraints(pattern=r"^(?:LI|SK)-\d+$"),
]

_MODEL_CONFIG = ConfigDict(extra="forbid", allow_inf_nan=False)


class ClusterDescriptor(BaseModel):
    """Properties of one cluster instance identified by Cluster Finder."""

    model_config = _MODEL_CONFIG

    size: int = Field(
        ge=2,
        description="Number of atomic sites in this cluster instance.",
    )
    averageDistance: float = Field(
        gt=0,
        description=(
            "Mean Cartesian distance, in angstrom, over the connected site pairs "
            "used by Cluster Finder for this cluster instance."
        ),
    )
    elements: list[ElementSymbol] = Field(
        min_length=2,
        description="Element symbol at each site in this cluster instance.",
    )
    isExtended: bool = Field(
        description=(
            "Whether supercell analysis identifies the cluster as part of an "
            "extended cluster network."
        )
    )
    isShared: bool = Field(
        description=(
            "Whether supercell analysis identifies sharing between periodic "
            "cluster images."
        )
    )

    @model_validator(mode="after")
    def validate_cluster(self) -> ClusterDescriptor:
        """Enforce invariants used when Cluster Finder created the CSV."""
        if len(self.elements) != self.size:
            raise ValueError("elements must contain exactly size entries")
        if self.isExtended and self.isShared:
            raise ValueError("isExtended and isShared cannot both be true")
        return self


class ClusterPointGroup(BaseModel):
    """Point-group assignment for one unique cluster type."""

    model_config = _MODEL_CONFIG

    label: ClusterLabel = Field(
        description="Cluster Finder label for the unique cluster type."
    )
    symbol: str = Field(
        min_length=1,
        description="Schoenflies point-group symbol of the unique cluster type.",
    )


class FlatBandProperties(BaseModel):
    """Selected flat-band model annotation from Neves et al. (2024)."""

    model_config = _MODEL_CONFIG

    sublatticeElement: ElementSymbol = Field(
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
    latticeDimensionalities: list[Literal[1, 2, 3]] = Field(
        min_length=1,
        description="Dimensionality of each classified flat-band lattice motif.",
    )
    latticeIds: list[FlatBandLatticeId] = Field(
        min_length=1,
        description=(
            "Flat-band lattice identifiers assigned by Neves et al.; LI denotes "
            "lattice-invariant classification and SK denotes Systre-key "
            "classification."
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
        if len(self.latticeDimensionalities) != len(self.latticeIds):
            raise ValueError(
                "latticeDimensionalities and latticeIds must have equal lengths"
            )
        return self


class ClusterMaterial(BaseModel):
    """Contributed cluster results for one Materials Project material."""

    model_config = _MODEL_CONFIG

    materialId: MaterialId = Field(
        description=(
            "Materials Project identifier used only as the external linkage key "
            "for this contribution."
        )
    )
    compoundSystem: CompoundSystem = Field(
        description=(
            "Transition-metal and anion pair used for the Cluster Finder search, "
            "formatted as primary-transition-metal-anion."
        )
    )
    numberOfClusters: int = Field(
        ge=1,
        description="Number of cluster instances reported for this material.",
    )
    clusters: list[ClusterDescriptor] = Field(
        min_length=1,
        description="Cluster instances identified in the material.",
    )
    clusterLatticeSpaceGroup: str = Field(
        min_length=1,
        description=(
            "Space-group symbol of the derived lattice whose sites are unique "
            "cluster centroids; this is not the parent material space group."
        ),
    )
    clusterPointGroups: list[ClusterPointGroup] = Field(
        min_length=1,
        description=(
            "Point groups of unique cluster types. Its length may be smaller than "
            "numberOfClusters when instances are symmetry-equivalent."
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
            "Minimum, in angstrom, of averageDistance over all reported cluster "
            "instances."
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
    hasFlatData: bool = Field(
        description=(
            "Whether this material has a cited flat-band record in the reviewed "
            "flat-band source snapshot."
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

    @model_validator(mode="after")
    def validate_material(self) -> ClusterMaterial:
        """Enforce cross-field invariants for the contributed cluster data."""
        if len(self.clusters) != self.numberOfClusters:
            raise ValueError("numberOfClusters must equal len(clusters)")

        minimum = min(cluster.averageDistance for cluster in self.clusters)
        if abs(minimum - self.minimumAverageDistance) > 1e-9:
            raise ValueError(
                "minimumAverageDistance must equal the minimum cluster distance"
            )

        labels = [point_group.label for point_group in self.clusterPointGroups]
        if len(labels) != len(set(labels)):
            raise ValueError("clusterPointGroups labels must be unique")

        if self.hasFlatData != (self.flatBand is not None):
            raise ValueError("hasFlatData must agree with the presence of flatBand")
        return self
