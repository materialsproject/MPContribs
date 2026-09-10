"""Schema for the per-contribution ``clusterPointGroups`` table."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


ClusterLabel = Annotated[
    str,
    StringConstraints(pattern=r"^X\d+$", max_length=16),
]

_MODEL_CONFIG = ConfigDict(extra="forbid", allow_inf_nan=False)


class ClusterPointGroup(BaseModel):
    """Point-group assignment for one row in ``clusterPointGroups``."""

    model_config = _MODEL_CONFIG

    label: ClusterLabel = Field(
        description="Cluster Finder label for the unique cluster type."
    )
    symbol: str = Field(
        min_length=1,
        max_length=16,
        description="Schoenflies point-group symbol of the unique cluster type.",
    )
