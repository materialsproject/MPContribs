"""Worker-facing upload contracts.

These are not used within the API server directly, but exist to provide consumers of the API
documentation of contracts expected when accepting json/jsonl payloads sent to S3.

Workers must be kept in sync (by hand) with these models of json/jsonl bodies.
TODO: pull into shared repo
"""

from typing import Any, Literal

from pydantic import BaseModel


class UpdateRecord(BaseModel):
    """One record in an ``update`` file body.

    identity: the composite key used to uniquely identify a single resource
    update: the information used to update the resource. Can update nested fields via dot notation. Ie.
    {"update": {"data.foo": "bar"}} would update Contribution.data.foo to "bar".
    """

    identity: dict[str, Any]
    update: dict[str, Any]


class RepinRecord(BaseModel):
    """One record in a ``repin`` file body: move a contribution's structure reference to another version.

    identity: the composite key locating the contribution whose pin should move.
    lineage_name: which structure lineage (by ``name``) on that contribution to re-point.
    to_version_id: the target S3 ``version_id`` to pin (must already exist for that lineage).
    mode: ``representation`` for a safe byte/format fix (the worker fans the new version out to the
        named referencers); ``physical`` asserts the structure itself changed, which the worker
        refuses to apply by a silent re-point (the affected contributions must be recomputed).
    """

    identity: dict[str, Any]
    lineage_name: str
    to_version_id: str
    mode: Literal["representation", "physical"] = "representation"
