"""Worker-facing upload contracts.

These are not used within the API server directly, but exist to provide consumers of the API
documentation of contracts expected when accepting json/jsonl payloads sent to S3.

Workers must be kept in sync (by hand) with these models.
TODO: pull into shared repo
"""

from typing import Any, Literal

from pydantic import BaseModel

ComponentKind = Literal["structure", "table", "attachment"]


class ContributionRow(BaseModel):
    """Documents the reserved component-reference columns of a bulk contribution row/record.

    This is NOT the full row shape — most of a row is free-form ``data`` columns. It documents only the
    three reserved columns and how their values relate a row to its component objects. In CSV each value
    is a comma-separated list of digests; in JSONL each is a JSON array (modeled here).

    Each value is the sha256 hash of the the component's bytes (mirrors the object key in S3).
    """

    structures: list[str] = []
    tables: list[str] = []
    attachments: list[str] = []


class UpdateRecord(BaseModel):
    """One record in an ``update`` file body.

    identity: the composite key used to uniquely identify a single resource
    update: the information used to update the resource. Can update nested fields via dot notation. Ie.
    {"update": {"data.foo": "bar"}} would update Contribution.data.foo to "bar".
    """

    identity: dict[str, Any]
    update: dict[str, Any]
