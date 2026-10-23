"""Subnet row schema for the native topologySubnets Table."""

from collections.abc import Sequence

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PositiveInt,
    field_validator,
    model_validator,
)

from .data import TopologyData, reject_boolean_number


class Topology(BaseModel):
    """One subnet from a successful, available parent topology result."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    subnetIndex: PositiveInt = Field(
        description="One-based subnet index within this Contribution's successful topology result."
    )
    singleAllAgree: bool = Field(
        description="Recorded agreement between the SingleNodes and AllNodes representations."
    )
    singleNodeDimension: int = Field(
        ge=0, le=3, description="SingleNodes network dimension, 0 to 3, dimensionless."
    )
    singleNodeTopologyKey: str = Field(
        min_length=1,
        description="Nonblank SingleNodes topology key from the successful source result.",
    )
    singleNodeTopologyName: str | None = Field(
        default=None,
        description="Recorded SingleNodes topology name; original empty strings are retained.",
    )
    singleNodeTopologicalGenome: str | None = Field(
        default=None,
        description="Recorded SingleNodes topological genome; original empty strings are retained.",
    )
    allNodeDimension: int = Field(
        ge=0, le=3, description="AllNodes network dimension, 0 to 3, dimensionless."
    )
    allNodeTopologyKey: str = Field(
        min_length=1,
        description="Nonblank AllNodes topology key from the successful source result.",
    )
    allNodeTopologyName: str | None = Field(
        default=None,
        description="Recorded AllNodes topology name; original empty strings are retained.",
    )
    allNodeTopologicalGenome: str | None = Field(
        default=None,
        description="Recorded AllNodes topological genome; original empty strings are retained.",
    )

    @field_validator("singleNodeTopologyKey", "allNodeTopologyKey")
    @classmethod
    def validate_topology_key(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Topology key must contain a non-whitespace character")
        return value

    @model_validator(mode="after")
    def validate_agreement(self) -> "Topology":
        expected = self.singleNodeTopologyKey == self.allNodeTopologyKey
        if self.singleAllAgree != expected:
            raise ValueError("singleAllAgree must match the subnet topology keys")
        return self

    validate_numeric_inputs = field_validator(
        "subnetIndex",
        "singleNodeDimension",
        "allNodeDimension",
        mode="before",
    )(reject_boolean_number)


def validate_topology(summary: TopologyData, rows: Sequence[Topology]) -> None:
    """Validate a data.topology summary against its typed topologySubnets rows.

    Call after validating both components. Explicit null summaries are valid
    only when the corresponding subnet values are not all identical.
    This function checks results; it does not change availability or values.
    """
    if not isinstance(summary, TopologyData):
        raise TypeError("summary must be a validated TopologyData model")
    if any(not isinstance(row, Topology) for row in rows):
        raise TypeError("rows must contain validated Topology models")
    # Revalidate without computed/output conversion, including field presence.
    summary = TopologyData.model_validate(summary.model_dump(exclude_unset=True))
    rows = [Topology.model_validate(row.model_dump()) for row in rows]
    if not summary.topologyAvailable:
        if rows:
            raise ValueError("Unavailable topology must not contain subnet rows")
        return
    if not rows or summary.catenationDegree != len(rows):
        raise ValueError("catenationDegree must equal the positive subnet row count")

    indices = [row.subnetIndex for row in rows]
    if len(set(indices)) != len(indices):
        raise ValueError("subnetIndex must be unique within one Contribution")

    def common(values):
        distinct = set(values)
        return next(iter(distinct)) if len(distinct) == 1 else None

    expected = {
        "networkDimension": common(
            dimension
            for row in rows
            for dimension in (row.singleNodeDimension, row.allNodeDimension)
        ),
        "singleNodeNet": common(row.singleNodeTopologyKey for row in rows),
        "allNodeNet": common(row.allNodeTopologyKey for row in rows),
        "singleAllAgree": all(row.singleAllAgree for row in rows),
    }
    for name, value in expected.items():
        if getattr(summary, name) != value:
            raise ValueError(f"{name} does not match the topology subnet rows")
