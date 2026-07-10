import asyncio
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import cast

import structlog
from beanie import Link, PydanticObjectId
from pymongo import AsyncMongoClient
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import BulkWriteError

from mpcontribs_api.authz import User
from mpcontribs_api.config import MongoSettings, get_settings
from mpcontribs_api.domains._shared.bulk import (
    BulkDeleteSummary,
    BulkFailure,
    BulkWriteSummary,
    bulk_failure_from_exception,
)
from mpcontribs_api.domains._shared.repository import MongoDbRepository
from mpcontribs_api.domains.attachments.repository import MongoDbAttachmentRepository
from mpcontribs_api.domains.contributions.models import (
    Contribution,
    ContributionFilter,
    ContributionIn,
    ContributionPatch,
)
from mpcontribs_api.domains.contributions.pivot import expand_contribution, expand_data
from mpcontribs_api.domains.contributions.repository import MongoDbContributionRepository
from mpcontribs_api.domains.projects.repository import MongoDbProjectRepository
from mpcontribs_api.domains.structures.models import Structure
from mpcontribs_api.domains.structures.repository import MongoDbStructureRepository
from mpcontribs_api.domains.tables.models import Table
from mpcontribs_api.domains.tables.repository import MongoDbTableRepository
from mpcontribs_api.exceptions import AppError, ConflictError, NotFoundError, PermissionError, ValidationError
from mpcontribs_api.pagination import CursorParams

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class PreparedInput:
    """One expanded (pivoted) contribution paired with its original batch index and condition_key.

    Expansion can turn a single submitted contribution into many rows (see
    :func:`mpcontribs_api.domains.contributions.pivot.expand_contribution`); every row keeps the
    ``index`` of the submission it came from so per-item failures report against the original batch
    position, and carries the server-computed ``condition_key`` that (with project+identifier)
    identifies it.
    """

    index: int
    contribution: ContributionIn
    condition_key: str


@dataclass(frozen=True, slots=True)
class ResolvedWrite:
    """A contribution that passed validation, paired with its server-resolved version.

    Produced by the split pipeline so the resolved version travels with its contribution (and its
    original batch index and condition_key).
    """

    index: int
    contribution: ContributionIn
    version: int
    condition_key: str = ""


class ContributionService:
    def __init__(
        self,
        client: AsyncMongoClient,
        user: User,
        projects: MongoDbProjectRepository,
        contributions: MongoDbContributionRepository,
        structures: MongoDbStructureRepository,
        attachments: MongoDbAttachmentRepository,
        tables: MongoDbTableRepository,
        settings: MongoSettings | None = None,
    ):
        self._client = client
        self._user = user
        self._projects = projects
        self._contributions = contributions
        self._structures = structures
        self._attachments = attachments
        self._tables = tables
        self._settings = settings or get_settings().mongo

    @property
    def _children(self) -> dict[str, MongoDbRepository]:
        return {
            "structures": self._structures,
            "attachments": self._attachments,
            "tables": self._tables,
        }

    async def insert_contributions(
        self,
        contributions: list[ContributionIn],
    ) -> BulkWriteSummary[Contribution]:
        """Atomic bulk insert contributions, atomically per top-level contribution.

        Contributions carrying no components are inserted in one ``insert_many`` (no transaction);
        contributions with components run inside their own MongoDB transaction so the contribution
        and its components commit or roll back together. When a submission pivots into several rows
        that share components, all of those rows are written in one transaction and link to the
        components inserted once (deduplicated by content hash). Concurrent transactions are bounded
        by ``settings.mongo.max_concurrent_transactions``. Per-item failures are returned in the
        summary's ``failed`` list; the request as a whole does not raise on partial failure.

        Version is server-assigned per contribution: unique-identifier projects reject a duplicate
        (project, identifier) as a conflict (version stays 1); non-unique projects auto-increment
        from the current max. See ``_split_non_unique``.

        Args:
            contributions: contributions to insert; may include nested structures/tables/attachments

        Returns:
            BulkWriteSummary[Contribution]: per-item outcome, sized to ``len(contributions)``
        """
        if not contributions:
            return BulkWriteSummary[Contribution](total=0, succeeded=[], failed=[])

        failures, plan = await self._split_contributions(contributions, is_upsert=False)
        no_comp = [item for item in plan if not item.contribution.has_components()]
        with_comp = [item for item in plan if item.contribution.has_components()]

        no_comp_succeeded, no_comp_failed = await self._insert_no_components(no_comp)
        with_comp_succeeded, with_comp_failed = await self._insert_with_components(with_comp)

        succeeded = [doc for _, doc in sorted(no_comp_succeeded + with_comp_succeeded, key=lambda p: p[0])]
        failed = sorted(
            failures + no_comp_failed + with_comp_failed,
            key=lambda f: f.index,
        )
        return BulkWriteSummary[Contribution](total=len(contributions), succeeded=succeeded, failed=failed)

    def _expand_batch(
        self,
        contributions: list[ContributionIn],
    ) -> tuple[list[BulkFailure], list[PreparedInput]]:
        """Annotate units and pivot each submission on its conditions, keeping the original index.

        A submission may expand into several rows (one per condition signature) or be rejected as a
        whole (malformed annotation or colliding columns). Any components on the submission ride
        along on every resulting row (see :func:`...pivot.expand_contribution`). A rejection becomes
        a single ``BulkFailure`` against the submission's original index; every surviving row carries
        that index and its ``condition_key`` forward.
        """
        failures: list[BulkFailure] = []
        prepared: list[PreparedInput] = []
        for i, contrib in enumerate(contributions):
            try:
                rows = expand_contribution(contrib)
            except AppError as exc:
                failures.append(bulk_failure_from_exception(i, contrib.identifiers(), exc))
                logger.info("contribution expansion rejected", index=i, identifiers=contrib.identifiers())
                continue
            for row in rows:
                prepared.append(PreparedInput(index=i, contribution=row.contribution, condition_key=row.condition_key))
        return failures, prepared

    def _split_unauthorized(
        self,
        items: Iterable[PreparedInput],
    ) -> tuple[list[BulkFailure], list[PreparedInput]]:
        """Reject contributions whose ``project`` the current user is not permitted to write.

        Authorized iff the user is an admin (writes anything) or the contribution's ``project`` is
        one of the user's groups. Anonymous users are blocked at the router, but carry no groups and
        are not admins, so they fall through to authorized-for-nothing here (defense-in-depth).

        Partitions ``items`` into unauthorized ``BulkFailure`` entries and the remaining authorized
        items that should proceed. Mirrors ``_split_oversize`` (same shape) so callers can chain
        the splits and keep each item in exactly one bucket, preserving input ordering.
        """
        unauthorized: list[BulkFailure] = []
        remaining: list[PreparedInput] = []
        for item in items:
            contrib = item.contribution
            if self._user.can_write(contrib.project):
                remaining.append(item)
            else:
                unauthorized.append(
                    BulkFailure(
                        index=item.index,
                        identifier=contrib.identifiers(),
                        error_code=PermissionError.error_code,
                        message=f"not authorized to write to project '{contrib.project}'",
                    )
                )
                logger.warning(
                    "User attempted to add contributions to projects they are not authorized for.",
                    project=contrib.project,
                )
        return unauthorized, remaining

    async def _split_non_unique(
        self,
        items: Iterable[PreparedInput],
        *,
        is_upsert: bool,
    ) -> tuple[list[BulkFailure], list[ResolvedWrite]]:
        """Apply per-project identifier-uniqueness rules and resolve each contribution's version.

        ``Project.unique_identifiers`` decides the contract per project:

        - **True**: at most one contribution per (project, identifier); version is always 1. On
          insert a second one (already in the DB, or a duplicate earlier in this batch) is rejected
          as a conflict. On upsert the version is inferred as 1 (any supplied value is ignored).
        - **False**: many versions may share (project, identifier). On insert the version is
          auto-assigned as ``max(existing) + 1``, sequencing intra-batch duplicates. On upsert the
          caller may supply ``version`` to pick the target row; if omitted it defaults to 1 **only
          when no row yet exists** for that (project, identifier, condition_key) — an unambiguous
          insert. If a row already exists, an unversioned upsert is ambiguous (update which version
          vs insert a new one) and is rejected, requiring the caller to specify ``version``.

        Iterates ``items`` in input order so intra-batch duplicates sequence deterministically.
        Uniqueness and versioning key on (project, identifier, condition_key) so pivoted rows that
        differ only by condition are independent identities.

        Returns:
            tuple of (rejections, a ``ResolvedWrite`` per survivor pairing it with its version)
        """
        items = list(items)
        failures: list[BulkFailure] = []
        plan: list[ResolvedWrite] = []
        if not items:
            return failures, plan

        # One round-trip each for the per-project uniqueness flags and the current max version per
        # key, instead of a query per contribution. Insert needs the max for every key (assign next
        # version / reject unique-project dupes); upsert needs it only for non-unique projects, where
        # the presence of an existing row makes an unversioned upsert ambiguous (see below).
        unique_map = await self._projects.unique_identifiers_by_id(sorted({it.contribution.project for it in items}))
        max_map: dict[tuple[str, str, str], int] = {}
        if is_upsert:
            keys = sorted(
                {
                    (it.contribution.project, it.contribution.identifier, it.condition_key)
                    for it in items
                    if unique_map.get(it.contribution.project) is False
                }
            )
        else:
            keys = sorted({(it.contribution.project, it.contribution.identifier, it.condition_key) for it in items})
        if keys:
            max_map = await self._contributions.max_versions(keys)

        seen: dict[tuple[str, str, str], int] = defaultdict(int)
        for item in items:
            contrib = item.contribution
            key = (contrib.project, contrib.identifier, item.condition_key)

            if contrib.project not in unique_map:
                failures.append(
                    BulkFailure(
                        index=item.index,
                        identifier=contrib.identifiers(),
                        error_code=ValidationError.error_code,
                        message=f"project '{contrib.project}' not found or not accessible",
                    )
                )
                logger.info(
                    "project not found or not accessible",
                    project=contrib.project,
                    identifiers=contrib.identifiers(),
                )
                continue

            unique = unique_map[contrib.project]
            if is_upsert:
                if unique:
                    # At most one row per (project, identifier, condition_key); upsert is unambiguous.
                    version = 1
                elif contrib.version is not None:
                    version = contrib.version
                elif key in max_map or seen[key] > 0:
                    # Non-unique project with a row already present (in the DB, or planned earlier in
                    # this batch): an unversioned upsert is ambiguous — update which version, or
                    # insert a new one? Require the caller to specify a version to disambiguate.
                    failures.append(
                        BulkFailure(
                            index=item.index,
                            identifier=contrib.identifiers(),
                            error_code=ValidationError.error_code,
                            message=(
                                f"project '{contrib.project}' already has a contribution for identifier "
                                f"'{contrib.identifier}'; specify a 'version' to disambiguate updating an "
                                "existing version from inserting a new one"
                            ),
                        )
                    )
                    logger.info(
                        "ambiguous unversioned upsert with existing contributions",
                        project=contrib.project,
                        identifiers=contrib.identifiers(),
                    )
                    continue
                else:
                    # No existing row for this identity: an unversioned upsert is an unambiguous
                    # insert, so default to version 1 (backwards compatible).
                    version = 1
            elif unique:
                # Insert into a unique-identifier project: the first occurrence wins, anything that
                # already exists (in the DB or earlier in this batch) is a conflict.
                if key in max_map or seen[key] > 0:
                    failures.append(
                        BulkFailure(
                            index=item.index,
                            identifier=contrib.identifiers(),
                            error_code=ConflictError.error_code,
                            message=(
                                f"contribution '{contrib.identifier}' already exists for project '{contrib.project}'"
                            ),
                        )
                    )
                    logger.info(
                        "contribution already exists in project during insert/upsert/update",
                        project=contrib.project,
                        identifiers=contrib.identifiers(),
                    )
                    continue
                version = 1
            else:
                # Insert into a non-unique-identifier project: next version after the current max,
                # sequencing duplicates within this batch (max+1, max+2, ...).
                version = max_map.get(key, 0) + 1 + seen[key]

            plan.append(
                ResolvedWrite(index=item.index, contribution=contrib, version=version, condition_key=item.condition_key)
            )
            seen[key] += 1

        return failures, plan

    def _split_oversize(
        self,
        items: Iterable[PreparedInput],
    ) -> tuple[list[BulkFailure], list[PreparedInput]]:
        """Reject contributions whose component count exceeds the per-contribution ceiling.

        Partitions ``items`` into oversize ``BulkFailure`` entries and the remaining items that
        should proceed to Mongo. Doing this upfront avoids burning a transaction slot on a request
        guaranteed to exceed transactionLifetimeLimitSeconds.
        """
        cap = self._settings.max_components_per_contribution
        oversize: list[BulkFailure] = []
        remaining: list[PreparedInput] = []
        for item in items:
            contrib = item.contribution
            count = contrib.component_count()
            if count > cap:
                oversize.append(
                    BulkFailure(
                        index=item.index,
                        identifier=contrib.identifiers(),
                        error_code=ValidationError.error_code,
                        message=f"contribution has {count} components, exceeds cap of {cap}. "
                        "Recommend inserting the component alone, followed by bulk inserts of components",
                    )
                )
                logger.info("Attemped to add contribution with too many components.", num_components=count, max=cap)
            else:
                remaining.append(item)
        return oversize, remaining

    async def _split_contributions(
        self, contributions: list[ContributionIn], *, is_upsert: bool
    ) -> tuple[list[BulkFailure], list[ResolvedWrite]]:
        """Common method for validating contribution write failure logic and resolving versions.

        Expands (annotates units + pivots on conditions) each submission first, then runs the cheap,
        local, index-based filters (authorization, then component-count cap) so guaranteed failures
        never reach the DB; ``_split_non_unique`` runs last and turns the remaining items into a
        write plan carrying each resolved version and condition_key. Failures report against the
        original submission index even though one submission may have produced several rows.

        Returns:
            tuple of (failures and their reasons, a ``ResolvedWrite`` per contribution to write)
        """
        # Annotate units and pivot each submission on its conditions (1 submission -> N rows).
        expand_failures, prepared = self._expand_batch(contributions)
        # Bound the *expanded* row count: a small batch can pivot into many rows, so the router's
        # raw-count gate isn't enough on its own (advertised at GET /api/v1/limits).
        limit = self._settings.bulk_write_limit
        if len(prepared) > limit:
            raise ValidationError(
                f"Submission expands to {len(prepared)} contributions, exceeding the per-request limit of {limit}. "
                "Chunk the request (see GET /api/v1/limits) or use the async bulk ingestion endpoint.",
                expanded_count=len(prepared),
                limit=limit,
            )
        # Per-item project authorization (see _split_unauthorized for the per-item vs fail-fast
        # decision). Only authorized items reach Mongo; the rest are reported in ``failed``.
        unauthorized_failures, authorized = self._split_unauthorized(prepared)
        # Reject contributions that have too many components associated with them.
        oversize_failures, sized = self._split_oversize(authorized)
        # Verify identifiers/uniqueness within a project and resolve each version, depending on
        # project.unique_identifiers and whether this is an insert or upsert.
        non_unique_failures, plan = await self._split_non_unique(sized, is_upsert=is_upsert)
        return (expand_failures + unauthorized_failures + oversize_failures + non_unique_failures, plan)

    async def _insert_no_components(
        self,
        items: list[ResolvedWrite],
    ) -> tuple[list[tuple[int, Contribution]], list[BulkFailure]]:
        """Single-collection bulk insert for component-free contributions.

        Uses ``ordered=False`` so a single bad item doesn't sink the rest of the batch. pymongo
        raises ``BulkWriteError`` with per-index error info on partial failure; we map that back
        onto the original input indices.
        """
        if not items:
            return [], []
        docs = []
        for item in items:
            doc = Contribution.from_input_model(item.contribution)
            doc.version = item.version
            doc.condition_key = item.condition_key
            docs.append(doc)
        try:
            await self._contributions.insert_many_contributions(docs)
            return [(item.index, doc) for item, doc in zip(items, docs, strict=True)], []
        except BulkWriteError as exc:
            return self._partition_bulk_write_error(items, docs, exc)

    @staticmethod
    def _partition_bulk_write_error(
        items: list[ResolvedWrite],
        docs: list[Contribution],
        exc: BulkWriteError,
    ) -> tuple[list[tuple[int, Contribution]], list[BulkFailure]]:
        """Map pymongo's per-position writeErrors back to the caller's original input indices."""
        write_errors = exc.details.get("writeErrors", []) if exc.details else []
        failed_positions = {err.get("index"): err for err in write_errors}
        succeeded: list[tuple[int, Contribution]] = []
        failed: list[BulkFailure] = []
        for position, (item, doc) in enumerate(zip(items, docs, strict=True)):
            err = failed_positions.get(position)
            if err is None:
                succeeded.append((item.index, doc))
            else:
                failed.append(
                    BulkFailure(
                        index=item.index,
                        identifier=item.contribution.identifiers(),
                        error_code="conflict" if err.get("code") == 11000 else "write_error",
                        message=err.get("errmsg", "write failed"),
                    )
                )
        return succeeded, failed

    async def _insert_with_components(
        self,
        items: list[ResolvedWrite],
    ) -> tuple[list[tuple[int, Contribution]], list[BulkFailure]]:
        """Per-submission transaction path, bounded by ``max_concurrent_transactions``.

        Rows that pivoted out of the same submission share an ``index`` and carry identical component
        inputs (see :func:`mpcontribs_api.domains.contributions.pivot.expand_contribution`), so they
        are grouped and written together in one transaction: the shared components are inserted once
        (deduplicated by content hash in the components repo) and every row in the group links to the
        resulting ids. A submission that did not pivot is simply a group of one, preserving the
        previous one-transaction-per-row shape.
        """
        if not items:
            return [], []
        # Group by the original submission index (preserving first-seen order so the summary keeps
        # input ordering after the outer sort); pivoted rows of one submission share components.
        groups: dict[int, list[ResolvedWrite]] = defaultdict(list)
        for item in items:
            groups[item.index].append(item)
        sem = asyncio.Semaphore(self._settings.max_concurrent_transactions)

        async def _bounded(group: list[ResolvedWrite]) -> list[Contribution] | BulkFailure:
            async with sem:
                return await self._insert_group_with_components(group)

        grouped = list(groups.values())
        results = await asyncio.gather(*[_bounded(group) for group in grouped])
        succeeded: list[tuple[int, Contribution]] = []
        failed: list[BulkFailure] = []
        for group, outcome in zip(grouped, results, strict=True):
            if isinstance(outcome, BulkFailure):
                failed.append(outcome)
            else:
                succeeded.extend((group[0].index, doc) for doc in outcome)
        return succeeded, failed

    async def _insert_group_with_components(self, group: list[ResolvedWrite]) -> list[Contribution] | BulkFailure:
        """Run one submission's pivoted rows + their shared components inside a transaction.

        Uses ``session.with_transaction`` so transient txn errors (write conflicts, primary step-
        downs) get pymongo's retry treatment, and so the components and every pivoted row of the
        submission commit or roll back together. Any exception is converted to a single
        ``BulkFailure`` against the submission's index so the surrounding ``asyncio.gather`` sees a
        normal return value for every coroutine.
        """
        index = group[0].index
        contrib = group[0].contribution
        try:
            async with self._client.start_session() as session:

                async def _txn(s: AsyncClientSession) -> list[Contribution]:
                    return await self._do_insert_group(group, s)

                return await session.with_transaction(_txn)
        except AppError as exc:
            return bulk_failure_from_exception(index, contrib.identifiers(), exc)
        except Exception as exc:
            logger.error("insert_contribution_failed", index=index, identifier=contrib.identifiers(), exc_info=True)
            return bulk_failure_from_exception(index, contrib.identifiers(), exc)

    async def _do_insert_group(self, group: list[ResolvedWrite], session: AsyncClientSession) -> list[Contribution]:
        """Insert the submission's shared components once, then every pivoted row, all in ``session``.

        Every row in ``group`` came from the same submission and carries identical component inputs,
        so the components are inserted a single time — the components repo deduplicates by content
        hash and returns the already-stored document (its id) when the content exists — and each
        row's contribution links to those shared ids. Components are inserted sequentially because a
        session is single-threaded — sharing it across concurrent awaits would corrupt the wire
        protocol.
        """
        template = group[0].contribution
        structures = await self._structures.insert_components(template.structures or [], session=session)
        tables = await self._tables.insert_components(template.tables or [], session=session)
        struct_links = cast(list[Link[Structure]] | None, structures or None)
        table_links = cast(list[Link[Table]] | None, tables or None)

        inserted: list[Contribution] = []
        for item in group:
            doc = Contribution.from_input_model(item.contribution)
            doc.version = item.version
            doc.condition_key = item.condition_key
            doc.structures = struct_links
            doc.tables = table_links
            inserted.append(await self._contributions.insert_contribution(doc, session=session))
        return inserted

    async def upsert_contributions(self, contributions: list[ContributionIn]) -> BulkWriteSummary[Contribution]:
        """Upsert contributions by their identifying fields, reporting per-item outcomes.

        Components (structures, tables, attachments) must be managed via their respective
        services. If any contribution in the batch carries components, the entire request is
        rejected before any database writes occur.

        Each item is upserted atomically by ``ContributionIn.identifiers()`` via a single
        ``findOneAndUpdate(..., upsert=True)`` so two requests targeting the same key cannot
        race past the find branch — the unique index over those fields is the tiebreaker.
        Concurrent upserts within a batch are bounded by ``settings.mongo.max_concurrent_transactions``.
        A single item failing does not fail the batch: it is reported in ``failed`` while the others
        still commit (mirroring ``insert_contributions``).

        Args:
            contributions: contributions to upsert; must not include nested components

        Returns:
            BulkWriteSummary[Contribution]: per-item outcome, sized to ``len(contributions)``

        Raises:
            ValidationError: if any contribution in the batch carries components
        """
        if not contributions:
            return BulkWriteSummary[Contribution](total=0, succeeded=[], failed=[])

        indices_with_components = [i for i, c in enumerate(contributions) if c.has_components()]
        if indices_with_components:
            raise ValidationError(
                "Components must be managed via their respective services, not via contribution upsert.",
                contribution_indices=indices_with_components,
            )

        failures, plan = await self._split_contributions(contributions, is_upsert=True)

        sem = asyncio.Semaphore(self._settings.max_concurrent_transactions)

        async def _bounded_upsert(item: ResolvedWrite) -> Contribution | BulkFailure:
            contrib = item.contribution
            # identifiers() carries the raw request version; override it with the version the service
            # resolved (unique -> 1, non-unique -> supplied/defaulted) so the repo targets the right row.
            identifiers = {**contrib.identifiers(), "version": item.version}
            async with sem:
                try:
                    return await self._contributions.upsert_contribution_by_identifiers(
                        identifiers, contrib, item.condition_key
                    )
                except Exception as exc:
                    logger.error(
                        "upsert_contribution_failed", index=item.index, identifier=contrib.identifiers(), exc_info=True
                    )
                    return bulk_failure_from_exception(item.index, contrib.identifiers(), exc)

        results = await asyncio.gather(*[_bounded_upsert(item) for item in plan])
        succeeded = [r for r in results if not isinstance(r, BulkFailure)]
        failed = failures + [r for r in results if isinstance(r, BulkFailure)]
        return BulkWriteSummary[Contribution](total=len(contributions), succeeded=succeeded, failed=failed)

    async def patch_contribution(self, id: str, patch: ContributionPatch) -> list[Contribution]:
        """Partially update a contribution, fanning condition-bearing ``data`` onto its pivoted rows.

        The ``{id}`` in the path anchors the update: its stored ``(project, identifier, version)`` is
        the identity all matched rows share. ``data`` is run through the same annotated-key machinery
        as inserts (:func:`expand_data`), so units are canonicalized and conditions become columns.

        - **No conditions in ``data``** (or no ``data`` at all): a plain partial update of the target
          row itself. Units are still annotated; the row's ``condition_key`` is unchanged.
        - **Conditions present:** the patch *fans out*. Each condition signature is applied to the
          existing sibling row that already carries the matching ``condition_key`` (under the target's
          project/identifier/version). A ``condition_key`` is never rewritten, and no new rows are
          created: a signature with no matching stored row is rejected.

        Non-``data`` fields set on the patch are applied to every row the patch touches.

        Args:
            id: the id of a contribution the caller may see; anchors the (project, identifier, version)
            patch: the partial update; ``data`` may carry unit/condition annotations

        Returns:
            list[Contribution]: the updated document(s), one per row the patch touched

        Raises:
            NotFoundError: if no in-scope contribution has that id
            PermissionError: if the caller may not write the target's project
            ValidationError: on a malformed/oversize ``data`` annotation, or a condition signature
                with no matching stored row
        """
        target = await self._contributions.get_contribution_document(id)
        if target is None:
            raise NotFoundError(f"Contribution with id {id} not found", id=id)
        if not self._user.can_write(target.project):
            raise PermissionError(f"not authorized to write to project '{target.project}'")

        # Non-data fields patch through unchanged
        # data is handled separately because it may expand into several rows.
        scalar_update = patch.model_dump(exclude_unset=True, exclude={"data"})

        # No data change: behave like a plain single-row patch of the target (no-op if nothing set).
        if patch.data is None:
            if not scalar_update:
                return [target]
            updated = await self._contributions.patch_pivot_row(
                target.project, target.identifier, target.version, target.condition_key, scalar_update
            )
            return [updated] if updated is not None else []

        rows = expand_data(patch.data)

        # No conditions: single row targeting the {id} contribution itself (units annotated in place).
        if not any(row.condition_key for row in rows):
            update_data = {**scalar_update, "data": rows[0].data}
            updated = await self._contributions.patch_pivot_row(
                target.project, target.identifier, target.version, target.condition_key, update_data
            )
            return [updated] if updated is not None else []

        # Conditions present: fan each signature onto the sibling row that already carries it. Missing
        # rows are rejected — a patch matches existing pivots, it never mints new condition_keys.
        updated_rows: list[Contribution] = []
        for row in rows:
            update_data = {**scalar_update, "data": row.data}
            updated = await self._contributions.patch_pivot_row(
                target.project, target.identifier, target.version, row.condition_key, update_data
            )
            if updated is None:
                raise ValidationError(
                    f"no existing contribution for project '{target.project}', identifier "
                    f"'{target.identifier}', version {target.version} with condition_key "
                    f"'{row.condition_key}'; a patch updates existing pivoted rows and cannot create new ones",
                    condition_key=row.condition_key,
                )
            updated_rows.append(updated)
        return updated_rows

    async def delete_contributions(self, filter: ContributionFilter) -> BulkDeleteSummary:
        """Delete a contribution and all of its child components

        Doesn't guarantee complete atomicity, but prevents orphaned children by deleting components first.

        Args:
            filter (ContributionFilter): the Contribution-specific query to apply on top of the user scope


        Returns:
            BulkDeleteSummary: a summary of how many documents and child documents were deleted
        """
        num_deleted_components = 0
        num_deleted_contributions = 0
        # Loop through cursor rather than materialize arbitrary number of Contributions
        while True:
            # Since we are deleting everything matching filter, we can continuously get the 1st page
            page = await self._contributions.get_contributions(
                pagination=CursorParams(cursor=None, limit=100),
                filter=filter,
            )
            # For each component type, gather ObjectIds then bulk delete them
            # - components first so no children are left orphaned
            for field, repo in self._children.items():
                ids = [link.ref.id for c in page.items for link in (getattr(c, field) or [])]
                if ids:
                    deleted_components = await repo.delete_by_ids(ids)
                    num_deleted_components += deleted_components.num_deleted if deleted_components else 0

            # Delete Contributions in this batch by ID
            # need to make a new filter so we don't eagerly delete all contributions before their components are deleted
            deleted_contribs = await self._contributions.delete_contributions(
                ContributionFilter(id__in=[cast(PydanticObjectId, c.id) for c in page.items])
            )
            num_deleted_contributions += deleted_contribs.deleted_count if deleted_contribs else 0
            if not page.items:
                break
        return BulkDeleteSummary(num_deleted=num_deleted_contributions, num_children_deleted=num_deleted_components)
