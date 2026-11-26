"""Explicit atom rows for the viewer-only clusterMemberships table."""

from __future__ import annotations

from emmet.core.mpid import MPID
from pydantic import BaseModel, ConfigDict, Field


class ClusterMembership(BaseModel):
    """One ordered atom/image in a cluster, without repeated coordinates or properties."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    materialId: MPID = Field(description="Original contribution MP identifier.")
    clusterIndex: int = Field(
        ge=0,
        le=31,
        description="Zero-based row position in the bound clusters table; not an X-label.",
    )
    memberIndex: int = Field(
        ge=0,
        le=15,
        description="Contiguous zero-based atom position within this cluster, preserving certified order.",
    )
    siteIndex: int = Field(
        ge=0,
        le=255,
        description="Zero-based atomic site in the exact final task structure identified by coreStructureId.",
    )
    imageA: int = Field(
        ge=-2,
        le=2,
        description="Signed integer periodic image along the pinned lattice a vector.",
    )
    imageB: int = Field(
        ge=-2,
        le=2,
        description="Signed integer periodic image along the pinned lattice b vector.",
    )
    imageC: int = Field(
        ge=-2,
        le=2,
        description="Signed integer periodic image along the pinned lattice c vector.",
    )


def group_memberships(rows, number_of_sites=None):
    """Validate member order, contiguous clusters and per-cluster uniqueness."""
    groups = []
    seen = set()
    for value in rows:
        row = (
            value
            if isinstance(value, ClusterMembership)
            else ClusterMembership.model_validate(value)
        )
        if row.clusterIndex == len(groups):
            groups.append([])
            seen = set()
        if row.clusterIndex != len(groups) - 1:
            raise ValueError("Cluster rows must be contiguous and in source order")
        group = groups[-1]
        if row.memberIndex != len(group):
            raise ValueError("memberIndex must be contiguous and retain original order")
        if number_of_sites is not None and row.siteIndex >= number_of_sites:
            raise ValueError("siteIndex exceeds the pinned structure")
        ref = (row.siteIndex, row.imageA, row.imageB, row.imageC)
        if ref in seen:
            raise ValueError("Duplicate site/image within one cluster")
        seen.add(ref)
        group.append(row)
    return groups
