"""Compact per-instance membership for the viewer-only clusterMemberships table."""

from __future__ import annotations

import re
import hashlib
import json
from typing import Annotated

from emmet.core.mpid import MPID
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator


def _not_boolean(value):
    if isinstance(value, bool):
        raise ValueError("Membership indices cannot be booleans")
    return value


Index = Annotated[int, BeforeValidator(_not_boolean)]
_SITE = re.compile(
    r"(0|[1-9][0-9]*)(?:@\((-?(?:0|[1-9][0-9]*)),(-?(?:0|[1-9][0-9]*)),(-?(?:0|[1-9][0-9]*))\))?"
)


def parse_site_references(value: str) -> list[tuple[int, int, int, int]]:
    """Parse ordered '2; 5@(1,0,-1)' members without eval or range expansion."""
    if not isinstance(value, str) or not 0 < len(value) <= 200000:
        raise ValueError("Invalid siteReferences string")
    tokens = value.split(";")
    if len(tokens) > 20000:
        raise ValueError("Too many cluster members")
    members = []
    for token in tokens:
        match = _SITE.fullmatch(token.strip())
        if match is None:
            raise ValueError(
                "Use siteIndex or siteIndex@(imageA,imageB,imageC), separated by semicolons"
            )
        member = tuple(int(v) if v is not None else 0 for v in match.groups())
        if any(abs(v) > 100000 for v in member):
            raise ValueError("Site/image exceeds the reviewed index budget")
        members.append(member)
    if len(members) != len(set(members)):
        raise ValueError("Duplicate site/image within a cluster instance")
    return members


def format_site_references(members) -> str:
    """Keep member order; omit a suffix only when all three offsets are zero."""
    value = "; ".join(
        str(site) + (f"@({a},{b},{c})" if (a, b, c) != (0, 0, 0) else "")
        for site, a, b, c in members
    )
    parse_site_references(value)
    return value


class ClusterMembership(BaseModel):
    """One cluster instance, with no repeated elements, distances or symbols."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    materialId: MPID = Field(description="Original contribution MP identifier.")
    clusterIndex: Index = Field(
        ge=0,
        description="Zero-based row position in the bound clusters table; not an X-label.",
    )
    siteReferences: str = Field(
        min_length=1,
        max_length=200000,
        description=(
            "Ordered semicolon-separated summary-site references, e.g. '0; 2@(1,0,-1)'. "
            "A bare index means zero image offsets. The optional integer triple "
            "translates along lattice a,b,c, not Cartesian x,y,z. Native member "
            "order is preserved; elements/coordinates come from the exact bound summary structure."
        ),
    )
    pointGroupRow: Index = Field(
        ge=0,
        description=(
            "Zero-based row position in the checksum-bound clusterPointGroups table "
            "whose symbol equals this instance's independently verified point group. "
            "When identical symbols occur on multiple type rows, use the first matching "
            "row. This is a symbol lookup, not a unique cluster-type/X-label assignment."
        ),
    )

    @field_validator("siteReferences")
    @classmethod
    def canonical_members(cls, value):
        """Normalize site references without changing their member order."""
        return format_site_references(parse_site_references(value))


def membership_hash(rows) -> str:
    """Bind the exact certified instance-to-site and point-group references."""
    clean = [
        ClusterMembership.model_validate(row).model_dump(mode="json") for row in rows
    ]
    return hashlib.sha256(
        json.dumps(
            clean, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()
