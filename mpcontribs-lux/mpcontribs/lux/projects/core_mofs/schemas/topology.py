"""Subnet row schema for the native topologySubnets Table."""

from pydantic import BaseModel, ConfigDict, Field, PositiveInt


class Topology(BaseModel):
    """One subnet from a successful, available parent topology result."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)

    subnetIndex: PositiveInt
    singleAllAgree: bool
    singleNodeDimension: int = Field(ge=0, le=3)
    singleNodeTopologyKey: str = Field(min_length=1)
    singleNodeTopologyName: str | None = None
    singleNodeTopologicalGenome: str | None = None
    allNodeDimension: int = Field(ge=0, le=3)
    allNodeTopologyKey: str = Field(min_length=1)
    allNodeTopologyName: str | None = None
    allNodeTopologicalGenome: str | None = None
