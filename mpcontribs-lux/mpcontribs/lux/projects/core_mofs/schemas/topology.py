"""Subnet row schema for the native topologySubnets Table."""

from pydantic import BaseModel, ConfigDict, Field, PositiveInt


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
        description="Nonempty SingleNodes topology key from the successful source result.",
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
        description="Nonempty AllNodes topology key from the successful source result.",
    )
    allNodeTopologyName: str | None = Field(
        default=None,
        description="Recorded AllNodes topology name; original empty strings are retained.",
    )
    allNodeTopologicalGenome: str | None = Field(
        default=None,
        description="Recorded AllNodes topological genome; original empty strings are retained.",
    )
