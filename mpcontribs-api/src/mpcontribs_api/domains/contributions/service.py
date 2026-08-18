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
    BulkUpdateSummary,
    BulkWriteSummary,
    bulk_failure_from_exception,
)
from mpcontribs_api.domains._shared.repository import MongoDbRepository
from mpcontribs_api.domains._shared.units import QuantityLeaf
from mpcontribs_api.domains.attachments.repository import MongoDbAttachmentRepository
from mpcontribs_api.domains.consumers.models import ConsumerSettings
from mpcontribs_api.domains.contributions.data import validate_contribution_data
from mpcontribs_api.domains.contributions.models import (
    Contribution,
    ContributionFilter,
    ContributionIdentity,
    ContributionIn,
    ContributionPatch,
    Scalar,
    extract_unique_value,
)
from mpcontribs_api.domains.contributions.pivot import expand_contribution
from mpcontribs_api.domains.contributions.repository import MongoDbContributionRepository
from mpcontribs_api.domains.projects.models import Column, Stats
from mpcontribs_api.domains.projects.repository import MongoDbProjectRepository
from mpcontribs_api.domains.structures.models import Structure
from mpcontribs_api.domains.structures.repository import MongoDbStructureRepository
from mpcontribs_api.domains.tables.models import Table
from mpcontribs_api.domains.tables.repository import MongoDbTableRepository
from mpcontribs_api.exceptions import AppError, ConflictError, NotFoundError, PermissionError, ValidationError
from mpcontribs_api.pagination import CursorParams

logger = structlog.get_logger(__name__)

# Upper bound on rejected identifiers attached to a single quota-breach log line, so an
# adversarial mega-batch can't blow up the log payload. The counts are always exact.
_QUOTA_LOG_IDENTIFIER_CAP = 100


@dataclass(frozen=True, slots=True)
class PreparedWrite:
    """One expanded (pivoted) contribution carried through the bulk-write pipeline.

    Every row keeps the ``index`` of the submission it came from so per-item failures report
    against the original batch position, and carries the server-computed ``condition_key`` that
    identifies it.

    ``unique_value`` is ``None`` until identity resolution promotes the project's ``unique_column``
    value out of the contribution's ``data``.
    """

    index: int
    contribution: ContributionIn
    condition_key: str
    unique_value: Scalar | None = None


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
        limits: ConsumerSettings | None = None,
    ):
        self._client = client
        self._user = user
        self._projects = projects
        self._contributions = contributions
        self._structures = structures
        self._attachments = attachments
        self._tables = tables
        self._settings = settings or get_settings().mongo
        self._limits = limits or ConsumerSettings()

    @property
    def _children(self) -> dict[str, MongoDbRepository]:
        return {
            "structures": self._structures,
            "attachments": self._attachments,
            "tables": self._tables,
        }

    async def _unapproved_stored_count(self, project_id: str) -> int | None:
        """Contributions already stored for an unapproved ``project_id``, else ``None``.

        Returns ``None`` when the quota does not apply — the project is approved, or it could not
        be read in the current scope (existence/permission is enforced on insert, not here). The
        caller turns the count into a remaining allowance against the cap.
        """
        project = await self._projects.get_by_id(project_id, fields=frozenset({"is_approved"}))
        if not project or project.is_approved:
            return None
        # Soft limit: this count feeds a non-atomic check-then-write, so concurrent writes to the
        # same project can overshoot the cap by a bounded amount. Acceptable for an anti-abuse quota.
        return await self._contributions.count_contributions_for_project(project_id)

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
        await self.update_project({doc.project for doc in succeeded})
        return BulkWriteSummary[Contribution](total=len(contributions), succeeded=succeeded, failed=failed)

    def _expand_batch(
        self,
        contributions: list[ContributionIn],
    ) -> tuple[list[BulkFailure], list[PreparedWrite]]:
        """Annotate units and pivot each submission on its conditions, keeping the original index."""
        failures: list[BulkFailure] = []
        prepared: list[PreparedWrite] = []
        for i, contrib in enumerate(contributions):
            try:
                rows = expand_contribution(contrib)
            except AppError as exc:
                failures.append(bulk_failure_from_exception(i, contrib.identity_dict(), exc))
                logger.info("contribution expansion rejected", index=i, identifiers=contrib.identity_dict())
                continue
            for row in rows:
                prepared.append(PreparedWrite(index=i, contribution=row.contribution, condition_key=row.condition_key))
        return failures, prepared

    def _split_unauthorized(
        self,
        items: Iterable[PreparedWrite],
    ) -> tuple[list[BulkFailure], list[PreparedWrite]]:
        """Reject contributions whose ``project`` the current user is not permitted to write.

        Partitions ``items`` into unauthorized ``BulkFailure`` entries and the remaining authorized
        items that should proceed. Mirrors ``_split_oversize`` (same shape) so callers can chain
        the splits and keep each item in exactly one bucket, preserving input ordering.
        """
        unauthorized: list[BulkFailure] = []
        remaining: list[PreparedWrite] = []
        for item in items:
            contrib = item.contribution
            if self._user.can_write(contrib.project):
                remaining.append(item)
            else:
                unauthorized.append(
                    BulkFailure(
                        index=item.index,
                        identifier=contrib.identity_dict(),
                        error_code=PermissionError.error_code,
                        message=f"not authorized to write to project '{contrib.project}'",
                    )
                )
                logger.warning(
                    "User attempted to add contributions to projects they are not authorized for.",
                    project=contrib.project,
                )
        return unauthorized, remaining

    async def _resolve_identity(
        self,
        items: Iterable[PreparedWrite],
        *,
        is_upsert: bool,
    ) -> tuple[list[BulkFailure], list[PreparedWrite]]:
        """Resolve each contribution's identity (``unique_value``) and reject duplicates.

        A project designates at most one ``unique_column``; its value is promoted from the
        contribution's ``data`` to ``unique_value`` in the identity tuple
        ``(project, material_id, chemical_system_id, formula, unique_value, condition_key)``. A
        contribution is rejected when:

        - its ``project`` is not found or not accessible;
        - the project sets a ``unique_column`` but the value is missing or non-scalar
        - (insert only) its identity collides with an existing document or with an earlier item in
          this batch. Collisions are conflicts, never silently disambiguated.

        On upsert no collision check runs: an existing identity is the update target, and two items
        with the same identity in one batch both reach the atomic upsert (the unique index is the
        race tiebreaker). Iterates ``indices`` in input order so duplicates are caught deterministically.

        Returns:
            tuple of (rejections, a ``PreparedWrite`` per survivor pairing it with its unique_value)
        """
        items = list(items)
        failures: list[BulkFailure] = []
        plan: list[PreparedWrite] = []
        if not items:
            return failures, plan

        # One round-trip for the per-project unique_column, instead of a query per contribution.
        unique_columns = await self._projects.unique_columns_by_id(
            sorted({item.contribution.project for item in items})
        )

        # First pass: validate accessibility + resolve each unique_value, collecting identity tuples
        # so the existence check can be batched into a single query. condition_key is server-computed
        # by pivot and carried on each PreparedWrite
        resolved: list[tuple[int, ContributionIn, Scalar | None, str]] = []
        keys: list[ContributionIdentity] = []
        for item in items:
            i, contrib, condition_key = item.index, item.contribution, item.condition_key
            if contrib.project not in unique_columns:
                failures.append(
                    BulkFailure(
                        index=i,
                        identifier=contrib.identity_dict(),
                        error_code=ValidationError.error_code,
                        message=f"project '{contrib.project}' not found or not accessible",
                    )
                )
                logger.info(
                    "project not found or not accessible",
                    project=contrib.project,
                    identifiers=contrib.identity_dict(),
                )
                continue

            unique_column = unique_columns[contrib.project]
            unique_value: Scalar | None = None
            if unique_column is not None:
                try:
                    unique_value = extract_unique_value(contrib.data, unique_column)
                except ValidationError as err:
                    failures.append(
                        BulkFailure(
                            index=i,
                            identifier=contrib.identity_dict(),
                            error_code=ValidationError.error_code,
                            message=err.message,
                        )
                    )
                    logger.info(
                        "missing or non-scalar unique_column value",
                        project=contrib.project,
                        identifiers=contrib.identity_dict(),
                    )
                    continue

            resolved.append((i, contrib, unique_value, condition_key))
            keys.append(contrib.identity(unique_value, condition_key))

        # Second pass (insert only): reject identity collisions against existing docs and earlier
        # items in this batch. Upsert skips this - an existing identity is the update target and the
        # unique index arbitrates intra-batch races.
        if is_upsert:
            plan.extend(
                PreparedWrite(index=i, contribution=contrib, unique_value=uv, condition_key=ckey)
                for i, contrib, uv, ckey in resolved
            )
            return failures, plan

        existing = await self._contributions.existing_identities(keys)
        seen: set[ContributionIdentity] = set()
        for i, contrib, unique_value, condition_key in resolved:
            key: ContributionIdentity = contrib.identity(unique_value, condition_key)
            if key in existing or key in seen:
                failures.append(
                    BulkFailure(
                        index=i,
                        identifier=contrib.identity_dict(unique_value, condition_key),
                        error_code=ConflictError.error_code,
                        message=f"a contribution with this identity already exists for project '{contrib.project}'",
                    )
                )
                logger.info(
                    "duplicate contribution identity",
                    project=contrib.project,
                    identifiers=contrib.identity_dict(unique_value, condition_key),
                )
                continue
            seen.add(key)
            plan.append(
                PreparedWrite(index=i, contribution=contrib, unique_value=unique_value, condition_key=condition_key)
            )

        return failures, plan

    def _split_oversize(
        self,
        items: Iterable[PreparedWrite],
    ) -> tuple[list[BulkFailure], list[PreparedWrite]]:
        """Reject contributions whose component count exceeds the per-contribution ceiling.

        Partitions ``items`` into oversize ``BulkFailure`` entries and the remaining items that
        should proceed to Mongo. Doing this upfront avoids burning a transaction slot on a request
        guaranteed to exceed transactionLifetimeLimitSeconds.
        """
        cap = self._settings.max_components_per_contribution
        oversize: list[BulkFailure] = []
        remaining: list[PreparedWrite] = []
        for item in items:
            contrib = item.contribution
            count = contrib.component_count()
            if count > cap:
                oversize.append(
                    BulkFailure(
                        index=item.index,
                        identifier=contrib.identity_dict(),
                        error_code=ValidationError.error_code,
                        message=f"contribution has {count} components, exceeds cap of {cap}. "
                        "Recommend inserting the component alone, followed by bulk inserts of components",
                    )
                )
                logger.info("Attemped to add contribution with too many components.", num_components=count, max=cap)
            else:
                remaining.append(item)
        return oversize, remaining

    async def _split_quota_exceeded(
        self,
        plan: list[PreparedWrite],
        *,
        is_upsert: bool,
    ) -> tuple[list[BulkFailure], list[PreparedWrite]]:
        """Trim each unapproved project's newly-created contributions to its remaining quota."""
        by_project: dict[str, list[PreparedWrite]] = defaultdict(list)
        for item in plan:
            by_project[item.contribution.project].append(item)

        cap = self._limits.max_unapproved_contributions_per_project
        failures: list[BulkFailure] = []
        survivors: list[PreparedWrite] = []
        for project_id, items in by_project.items():
            stored = await self._unapproved_stored_count(project_id)
            if stored is None:
                survivors.extend(items)
                continue
            # Upserts against an existing row are updates (no new document); only absent identities count.
            existing = await self._existing_identities(items) if is_upsert else set()
            allowed = max(0, cap - stored)
            rejected: list[PreparedWrite] = []
            for item in items:
                identity = item.contribution.identity(item.unique_value, item.condition_key)
                if identity in existing:
                    survivors.append(item)
                elif allowed > 0:
                    survivors.append(item)
                    allowed -= 1
                else:
                    rejected.append(item)
            if not rejected:
                continue

            rejected_identifiers = [item.contribution.material_id for item in rejected[:_QUOTA_LOG_IDENTIFIER_CAP]]
            if len(rejected_identifiers):
                logger.warning(
                    "contribution.unapproved_quota_exceeded",
                    project=project_id,
                    max_allowed=cap,
                    stored=stored,
                    attempted=len(items) + len(rejected),
                    accepted=len(items),
                    rejected=len(rejected),
                    rejected_identifiers=rejected_identifiers,
                    rejected_identifiers_truncated=len(rejected) > _QUOTA_LOG_IDENTIFIER_CAP,
                )
            exc = PermissionError(
                "Attempted to add more than the allowed number of unapproved contributions",
                project=project_id,
                max_allowed=cap,
            )
            failures.extend(
                bulk_failure_from_exception(item.index, item.contribution.identity_dict(), exc) for item in rejected
            )
        survivors.sort(key=lambda item: item.index)
        return failures, survivors

    async def _existing_identities(self, items: list[PreparedWrite]) -> set[ContributionIdentity]:
        """Return which of ``items``' identities already have a stored document."""
        identities = [item.contribution.identity(item.unique_value, item.condition_key) for item in items]
        return await self._contributions.existing_identities(identities)

    @staticmethod
    def _log_quota_exceeded(
        project_id: str,
        cap: int,
        stored: int,
        accepted: int,
        rejected: list[PreparedWrite],
    ) -> None:
        """Emit a structured audit event for an unapproved-project quota breach.

        Request/user correlation (``consumer_id``, ``request_id``, ``trace_id``) is merged from the
        per-request contextvars, so only the domain-specific dimensions are added here. The rejected
        identifier list is capped to keep a pathological batch from bloating a single log line.
        """
        rejected_identifiers = [item.contribution.material_id for item in rejected[:_QUOTA_LOG_IDENTIFIER_CAP]]
        logger.warning(
            "contribution.unapproved_quota_exceeded",
            project=project_id,
            max_allowed=cap,
            stored=stored,
            attempted=accepted + len(rejected),
            accepted=accepted,
            rejected=len(rejected),
            rejected_identifiers=rejected_identifiers,
            rejected_identifiers_truncated=len(rejected) > _QUOTA_LOG_IDENTIFIER_CAP,
        )

    async def _split_contributions(
        self, contributions: list[ContributionIn], *, is_upsert: bool
    ) -> tuple[list[BulkFailure], list[PreparedWrite]]:
        """Common method for validating contribution write failure logic and resolving identity.

        Runs the cheap, local, index-based filters first (authorization, then component-count cap)
        so guaranteed failures never reach the DB; ``_resolve_identity`` runs last and turns the
        remaining indices into a write plan carrying each resolved ``unique_value``.

        Returns:
            tuple of (failures and their reasons, a ``PreparedWrite`` per contribution to write)
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
        # Resolve each contribution's identity (unique_value from the project's unique_column) and
        # reject duplicates, per project config and whether this is an insert or upsert.
        identity_failures, plan = await self._resolve_identity(sized, is_upsert=is_upsert)
        # Reject writes that would push an unapproved project past its contribution cap.
        quota_failures, plan = await self._split_quota_exceeded(plan, is_upsert=is_upsert)
        return (unauthorized_failures + oversize_failures + identity_failures + quota_failures, plan)

    async def _insert_no_components(
        self,
        items: list[PreparedWrite],
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
            doc.unique_value = item.unique_value
            doc.condition_key = item.condition_key
            docs.append(doc)
        try:
            await self._contributions.insert_many_contributions(docs)
            return [(item.index, doc) for item, doc in zip(items, docs, strict=True)], []
        except BulkWriteError as exc:
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
                            identifier=item.contribution.identity_dict(item.unique_value, item.condition_key),
                            error_code="conflict" if err.get("code") == 11000 else "write_error",
                            message=err.get("errmsg", "write failed"),
                        )
                    )
            return succeeded, failed

    async def _insert_with_components(
        self,
        items: list[PreparedWrite],
    ) -> tuple[list[tuple[int, Contribution]], list[BulkFailure]]:
        """Per-submission transaction path, bounded by ``max_concurrent_transactions``.

        Rows that pivoted out of the same submission share an ``index`` and carry identical component
        inputs, so they are grouped and written together in one transaction: the shared components are
        inserted once and every row in the group links to the resulting ids.
        """
        if not items:
            return [], []
        # Group by the original submission index (preserving first-seen order so the summary keeps
        # input ordering after the outer sort); pivoted rows of one submission share components.
        groups: dict[int, list[PreparedWrite]] = defaultdict(list)
        for item in items:
            groups[item.index].append(item)
        sem = asyncio.Semaphore(self._settings.max_concurrent_transactions)

        async def _bounded(group: list[PreparedWrite]) -> list[Contribution] | BulkFailure:
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

    async def _insert_group_with_components(self, group: list[PreparedWrite]) -> list[Contribution] | BulkFailure:
        """Run one submission's pivoted rows + their shared components inside a transaction.

        Uses transactions to keep a contribution and its components in-sync. Failed writes are returned as BulkFailures.
        """
        index = group[0].index
        contrib = group[0].contribution
        unique_value, condition_key = group[0].unique_value, group[0].condition_key
        try:
            async with self._client.start_session() as session:

                async def _txn(s: AsyncClientSession) -> list[Contribution]:
                    return await self._do_insert_group(group, s)

                return await session.with_transaction(_txn)
        except AppError as exc:
            return bulk_failure_from_exception(index, contrib.identity_dict(unique_value, condition_key), exc)
        except Exception as exc:
            logger.error(
                "insert_contribution_failed",
                index=index,
                identifier=contrib.identity_dict(unique_value, condition_key),
                exc_info=True,
            )
            return bulk_failure_from_exception(index, contrib.identity_dict(unique_value, condition_key), exc)

    async def _do_insert_group(self, group: list[PreparedWrite], session: AsyncClientSession) -> list[Contribution]:
        """Perform the insert of Contributions and their components within a single session."""
        template = group[0].contribution
        structures = await self._structures.insert_components(template.structures or [], session=session)
        tables = await self._tables.insert_components(template.tables or [], session=session)
        struct_links = cast(list[Link[Structure]] | None, structures or None)
        table_links = cast(list[Link[Table]] | None, tables or None)
        inserted: list[Contribution] = []
        for item in group:
            doc = Contribution.from_input_model(item.contribution)
            doc.unique_value = item.unique_value
            doc.condition_key = item.condition_key
            doc.structures = struct_links
            doc.tables = table_links
            inserted.append(await self._contributions.insert_contribution(doc, session=session))
        return inserted

    # TODO: Allow components to be upserted
    async def upsert_contributions(self, contributions: list[ContributionIn]) -> BulkWriteSummary[Contribution]:
        """Upsert contributions by their identifying fields, reporting per-item outcomes.

        Components (structures, tables, attachments) must be managed via their respective
        services. If any contribution in the batch carries components, the entire request is
        rejected before any database writes occur.

        Each item is upserted atomically by ``ContributionIn.identity_dict()`` via a single
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

        async def _bounded_upsert(item: PreparedWrite) -> Contribution | BulkFailure:
            contrib = item.contribution
            identifiers = contrib.identity_dict(item.unique_value, item.condition_key)
            async with sem:
                try:
                    return await self._contributions.upsert_contribution_by_identifiers(identifiers, contrib)
                except Exception as exc:
                    logger.error("upsert_contribution_failed", index=item.index, identifier=identifiers, exc_info=True)
                    return bulk_failure_from_exception(item.index, identifiers, exc)

        results = await asyncio.gather(*[_bounded_upsert(item) for item in plan])
        succeeded = [r for r in results if not isinstance(r, BulkFailure)]
        failed = failures + [r for r in results if isinstance(r, BulkFailure)]
        await self.update_project({doc.project for doc in succeeded})
        return BulkWriteSummary[Contribution](total=len(contributions), succeeded=succeeded, failed=failed)

    async def bulk_update(
        self,
        filter: ContributionFilter,
        update: ContributionPatch,
        *,
        replace_data: bool = False,
    ) -> BulkUpdateSummary:
        """Apply a filtered patch to every contribution matching ``filter`` the caller may write.

        Updates constrained to user's scope. Only the touched projects' rollups are recomputed.

        Two shapes, chosen by which fields the patch touches:

        - **Fast path** — the patch touches no identity input. A single ``$set`` is applied to every
          matched row in one ``update_many``.
        - **Per-row path** — the patch changes an Identifer field (or ``data``). Each matched row is
          patched individually via ``patch_contribution_by_id`` and any per-row conflict is reported
          in ``failed``.

        A ``data`` patch deep-merges into each row's stored ``data`` by default (unmentioned leaves
        survive); pass ``replace_data`` to overwrite the whole ``data`` dict instead.

        Args:
            filter: the contributions to target, applied on top of the user scope
            update: the fields to patch; unset fields are left untouched
            replace_data: overwrite ``data`` wholesale rather than merging into the stored dict

        Returns:
            BulkUpdateSummary: matched/modified counts, the projects touched, and per-row failures
        """
        fields = update.model_dump(exclude_unset=True)
        if not fields:
            # Nothing to set: MongoDB rejects an empty $set, so short-circuit with a no-op result.
            return BulkUpdateSummary(matched=0, modified=0, projects=[])
        filter = (
            filter
            if self._user.is_admin
            else filter.model_copy(update={"project__in": sorted(self._user.writable_projects)})
        )

        touches_identity = bool(ContributionIdentity.model_fields() & fields.keys()) or "data" in fields
        if not touches_identity:
            # No identity/unique_value recompute needed, so a uniform $set is safe.
            summary = await self._contributions.bulk_update(filter, fields)
            await self.update_project(project_ids=summary.projects)
            return summary

        return await self._bulk_patch_per_row(filter, update, replace_data=replace_data)

    async def _bulk_patch_per_row(
        self,
        filter: ContributionFilter,
        update: ContributionPatch,
        *,
        replace_data: bool = False,
    ) -> BulkUpdateSummary:
        """Patch each row matching ``filter`` individually.

        Concurrently validates reach contribution's identity, reporting failures in ``BulkUpdateSummary.failed``.
        """
        ids = await self._contributions.get_contribution_ids(filter)
        if not ids:
            return BulkUpdateSummary(matched=0, modified=0, projects=[])

        sem = asyncio.Semaphore(self._settings.max_concurrent_transactions)

        async def _patch_one(index: int, oid: PydanticObjectId) -> Contribution | BulkFailure:
            async with sem:
                try:
                    return await self.patch_contribution_by_id(str(oid), update, replace_data=replace_data)
                except Exception as exc:
                    logger.info("bulk_patch_item_failed", id=str(oid))
                    return bulk_failure_from_exception(index, {"id": str(oid)}, exc)

        results = await asyncio.gather(*[_patch_one(i, oid) for i, oid in enumerate(ids)])
        succeeded = [r for r in results if not isinstance(r, BulkFailure)]
        failed = [r for r in results if isinstance(r, BulkFailure)]
        projects = {doc.project for doc in succeeded if doc.project is not None}
        # Update the project to keep columns and stats in-sync
        await self.update_project(projects)
        return BulkUpdateSummary(matched=len(ids), modified=len(succeeded), projects=sorted(projects), failed=failed)

    async def _resolve_unique_value(self, project: str, data: dict | None) -> Scalar | None:
        """Resolve the identity value for one contribution from its project's ``unique_column``.

        Returns ``None`` when the project designates no ``unique_column`` (or is not accessible).
        Raises ``ValidationError`` when a ``unique_column`` is set but its value is missing/non-scalar.
        """
        columns = await self._projects.unique_columns_by_id([project])
        unique_column = columns.get(project)
        if unique_column is None:
            return None
        return extract_unique_value(data, unique_column)

    async def upsert_contribution_by_id(self, id: str, contribution: ContributionIn) -> Contribution:
        """Upsert a single contribution by Mongo id, resolving its server-owned ``unique_value``."""
        if not self._user.can_write(contribution.project):
            raise PermissionError(f"not authorized to write to project '{contribution.project}'")
        existing = await self._contributions.get_contribution_by_id(id, fields=None)
        if existing is None:
            stored = await self._unapproved_stored_count(contribution.project)
            cap = self._limits.max_unapproved_contributions_per_project
            if stored is not None and stored >= cap:
                raise PermissionError(
                    "Attempted to add more than the allowed number of unapproved contributions",
                    project=contribution.project,
                    max_allowed=cap,
                )
        unique_value = await self._resolve_unique_value(contribution.project, contribution.data)
        return await self._contributions.upsert_contribution_by_id(id, contribution, unique_value)

    async def patch_contribution_by_id(
        self, id: str, update: ContributionPatch, *, replace_data: bool = False
    ) -> Contribution:
        """Patch a single contribution by id.

        Re-reads the existing document when the patch touches identity inputs, to (a) recompute
        ``unique_value`` when ``data``/``project`` change and (b) validate the identifier hierarchy
        against the *merged* state when ``material_id``/``chemical_system_id``/``formula``. Metadata-only
        patches (e.g. ``is_public``) skip the read entirely, so they don't risk failing on a legacy document
        missing the unique_column value.

        ``data`` additively merges into the stored dict by default so unmentioned leaves survive (a
        bare scalar routes onto a stored quantity leaf's ``value``); pass ``replace_data`` to overwrite
        the whole ``data`` dict. On replace the payload becomes a standalone document, so it is
        re-validated strictly (the permissive patch validator allows leaf fragments a full doc may not).
        ``unique_value`` is resolved against the same post-write view the repository will persist.
        """
        set_fields = update.model_dump(exclude_unset=True)
        touches_unique = "data" in set_fields or "project" in set_fields
        touches_identity = bool(ContributionIdentity.HIERARCHY_FIELDS & set_fields.keys())
        if not touches_unique and not touches_identity:
            return await self._contributions.patch_contribution_by_id(id, update)

        if replace_data and set_fields.get("data") is not None:
            # A whole-dict overwrite must satisfy the strict insert-path rules (no leaf fragments).
            validate_contribution_data(set_fields["data"])

        existing = await self._contributions.get_contribution_by_id(id, fields=None)
        if existing is None or existing.project is None:
            raise NotFoundError(f"contribution '{id}' not found")

        if touches_identity:
            self._validate_identifier_hierarchy_merged(
                set_fields,
                existing_material_id=existing.material_id,
                existing_chemical_system_id=existing.chemical_system_id,
                existing_formula=existing.formula,
            )
        if not touches_unique:
            return await self._contributions.patch_contribution_by_id(id, update)

        project = set_fields.get("project") or existing.project
        # Resolve unique_value against the data the write will actually leave behind: the merged view
        # when merging (so an untouched unique_column value survives), or the patch's data on replace.
        if "data" not in set_fields:
            data = existing.data
        elif replace_data:
            data = set_fields["data"]
        else:
            data = QuantityLeaf.merge_data(existing.data, set_fields["data"])
        unique_value = await self._resolve_unique_value(project, data)
        return await self._contributions.patch_contribution_by_id(
            id, update, unique_value=unique_value, replace_data=replace_data, existing_data=existing.data
        )

    @staticmethod
    def _validate_identifier_hierarchy_merged(
        set_fields: dict,
        *,
        existing_material_id: str | None,
        existing_chemical_system_id: str | None,
        existing_formula: str | None,
    ) -> None:
        """Reject a patch whose merged identity violates chemical_system_id > formula > material_id.

        The merged value of each identity field is the patched value when set (``exclude_unset``, so
        an explicit ``null`` counts) and the existing document's value otherwise.
        """
        chemical_system_id = (
            set_fields["chemical_system_id"] if "chemical_system_id" in set_fields else existing_chemical_system_id
        )
        material_id = set_fields["material_id"] if "material_id" in set_fields else existing_material_id
        formula = set_fields["formula"] if "formula" in set_fields else existing_formula
        ContributionIdentity.check_hierarchy(material_id, chemical_system_id, formula)

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
        # Projects touched by this delete, so their rollup stats can be recomputed once at the end.
        affected_projects: set[str] = set()
        # Loop through cursor rather than materialize arbitrary number of Contributions
        while True:
            # Since we are deleting everything matching filter, we can continuously get the 1st page
            page = await self._contributions.get_contributions(
                pagination=CursorParams(cursor=None, limit=100),
                filter=filter,
            )
            affected_projects.update(c.project for c in page.items if c.project is not None)
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
        await self.update_project(affected_projects)
        return BulkDeleteSummary(num_deleted=num_deleted_contributions, num_children_deleted=num_deleted_components)

    async def update_project(self, project_ids: Iterable[str]) -> None:
        """Recompute ``Project.stats``/``Project.columns`` from current contributions, per project.

        Called after a write/delete. Uses the DB directly rather than a delta from the operation.

        The recompute is best-effort: a failure to refresh one project's stats is logged and does
        not fail the originating write.
        """
        pids = {pid for pid in project_ids if pid}
        if not pids:
            return
        updates: dict[str, tuple[Stats, list[Column]]] = {}
        for pid in sorted(pids):
            try:
                agg = await self._contributions.aggregate_project_stats(pid)
            except Exception:
                logger.error("project_stats_recompute_failed", project=pid, exc_info=True)
                continue
            stats = Stats(
                columns=len(agg.columns),
                contributions=agg.contributions,
                tables=agg.tables,
                structures=agg.structures,
                attachments=agg.attachments,
                size=agg.size,
            )
            columns = [Column(path=c.path, min=c.min, max=c.max, unit=c.unit) for c in agg.columns]
            updates[pid] = (stats, columns)
        await self._projects.set_stats_and_columns(updates)
