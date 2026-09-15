"""Schema for the per-contribution ``clusters`` table."""

from __future__ import annotations

from typing import Annotated

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

from .schema import _split_comma_separated


def _validate_elements(value: str) -> str:
    """Validate comma-separated element symbols while preserving the string."""
    try:
        for symbol in _split_comma_separated(value, "elements"):
            Element(symbol)
    except ValueError as exc:
        raise ValueError("elements contains an invalid element symbol") from exc
    return value


CommaSeparatedElements = Annotated[
    str,
    StringConstraints(min_length=1, max_length=128),
    AfterValidator(_validate_elements),
]

_MODEL_CONFIG = ConfigDict(extra="forbid", allow_inf_nan=False)


class Cluster(BaseModel):
    """Properties of one row in a contribution's ``clusters`` table."""

    model_config = _MODEL_CONFIG

    materialId: MPID = Field(
        description=(
            "Materials Project identifier linking this row to its parent "
            "ClusterMaterial contribution."
        )
    )
    size: int = Field(
        ge=2,
        description="Number of atomic sites in this cluster instance.",
    )
    averageDistance: float = Field(
        gt=0,
        description=(
            "Mean Cartesian distance in angstroms over the connected site pairs "
            "used by Cluster Finder for this cluster instance."
        ),
    )
    elements: CommaSeparatedElements = Field(
        description=(
            "Comma-separated element symbols in site order for this cluster "
            "instance."
        ),
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
    def validate_cluster(self) -> Cluster:
        """Enforce invariants used when Cluster Finder created the source data."""
        if len(self.elements.split(",")) != self.size:
            raise ValueError("elements must contain exactly size entries")
        if self.isExtended and self.isShared:
            raise ValueError("isExtended and isShared cannot both be true")
        return self
