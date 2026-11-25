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
        strict=True,
    )
    memberIndex: int = Field(
        ge=0,
        le=15,
        strict=True,
        description="Contiguous zero-based atom position within this cluster, preserving certified order.",
    )
    siteIndex: int = Field(
        ge=0,
        le=255,
        strict=True,
        description="Zero-based atomic site in the exact final task structure identified by coreStructureId.",
    )
    imageA: int = Field(
        ge=-2,
        le=2,
        strict=True,
        description="Signed integer periodic image along the pinned lattice a vector.",
    )
    imageB: int = Field(
        ge=-2,
        le=2,
        strict=True,
        description="Signed integer periodic image along the pinned lattice b vector.",
    )
    imageC: int = Field(
        ge=-2,
        le=2,
        strict=True,
        description="Signed integer periodic image along the pinned lattice c vector.",
    )
    pointGroupRow: int = Field(
        ge=0,
        le=31,
        description=(
            "Zero-based row position in the checksum-bound clusterPointGroups table "
            "whose symbol equals this instance's independently verified point group. "
            "When identical symbols occur on multiple type rows, use the first matching "
            "row. This is a symbol lookup, not a unique cluster-type/X-label assignment."
        ),
        strict=True,
    )


def group_memberships(rows, number_of_sites=None):
    """Validate order, coverage, symbol consistency and per-cluster uniqueness."""
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
        if group and row.pointGroupRow != group[0].pointGroupRow:
            raise ValueError("A cluster has conflicting point-group references")
        ref = (row.siteIndex, row.imageA, row.imageB, row.imageC)
        if ref in seen:
            raise ValueError("Duplicate site/image within one cluster")
        seen.add(ref)
        group.append(row)
    return groups
