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


class ProjectInitiativeAssignment(BaseModel):
    """Documents the initiative-assignment rules the worker must enforce for a ``project.json``.

    A ``project.json`` payload may carry an ``initiative`` field addressing the target initiative by
    its id or its slug (``None``/absent leaves the project unassigned). The API only authorizes
    project-write access (see the manifest ``authz`` block); it does **not** enforce initiative
    assignment anymore. When the worker applies a project write that sets ``initiative``, it MUST
    enforce the following (previously enforced in-app by ``ProjectService``):

    - **Both-rights / manage check:** the uploading user must be able to *manage* the target
      initiative — i.e. be its owner, a collaborator on it, or an admin. A user who can write the
      project but cannot manage the initiative must be rejected.
    - **Unapproved member cap:** if the target initiative is *not approved*, assigning the project
      must not push the initiative's assigned-project count past its per-initiative cap
      (``limits.initiative.max_projects_per_unapproved``). Re-assigning an already-assigned project
      is idempotent (exclude the project itself from the count).

    The ``authz`` block in the session manifest (``username``, ``is_admin``, ``project_role``)
    carries the identity under which the upload was accepted so the worker can make these checks.
    """

    # id or slug of the target initiative; None/absent => unassign.
    initiative: str | None = None
