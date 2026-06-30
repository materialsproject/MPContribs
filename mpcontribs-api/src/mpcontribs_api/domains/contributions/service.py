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
from mpcontribs_api.domains.contributions.models import Contribution, ContributionFilter, ContributionIn
from mpcontribs_api.domains.contributions.repository import MongoDbContributionRepository
from mpcontribs_api.domains.projects.repository import MongoDbProjectRepository
from mpcontribs_api.domains.structures.models import Structure
from mpcontribs_api.domains.structures.repository import MongoDbStructureRepository
from mpcontribs_api.domains.tables.models import Table
from mpcontribs_api.domains.tables.repository import MongoDbTableRepository
from mpcontribs_api.exceptions import AppError, ConflictError, PermissionError, ValidationError
from mpcontribs_api.pagination import CursorParams

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ResolvedWrite:
    """A contribution that passed validation, paired with its server-resolved version.

    Produced by the split pipeline so the resolved version travels with its contribution (and its
    original batch index)
    """

    index: int
    contribution: ContributionIn
    version: int


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
        and its components commit or roll back together. Concurrent transactions are bounded by
        ``settings.mongo.max_concurrent_transactions``. Per-item failures are returned in the
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

    def _split_unauthorized(
        self,
        indices: Iterable[int],
        contributions: list[ContributionIn],
    ) -> tuple[list[BulkFailure], list[int]]:
        """Reject contributions whose ``project`` the current user is not permitted to write.

        Authorized iff the user is an admin (writes anything) or the contribution's ``project`` is
        one of the user's groups. Anonymous users are blocked at the router, but carry no groups and
        are not admins, so they fall through to authorized-for-nothing here (defense-in-depth).

        Partitions ``indices`` into unauthorized ``BulkFailure`` entries and the remaining authorized
        indices that should proceed. Mirrors ``_split_oversize`` (same shape) so callers can chain
        the splits and keep each index in exactly one bucket, preserving input ordering.
        """
        unauthorized: list[BulkFailure] = []
        remaining: list[int] = []
        for i in indices:
            contrib = contributions[i]
            if self._user.can_write(contrib.project):
                remaining.append(i)
            else:
                unauthorized.append(
                    BulkFailure(
                        index=i,
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
        indices: Iterable[int],
        contributions: list[ContributionIn],
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
          caller must supply ``version`` to pick the target row, else the item is rejected.

        Iterates ``indices`` in input order so intra-batch duplicates sequence deterministically.

        Returns:
            tuple of (rejections, a ``ResolvedWrite`` per survivor pairing it with its version)
        """
        indices = list(indices)
        failures: list[BulkFailure] = []
        plan: list[ResolvedWrite] = []
        if not indices:
            return failures, plan

        # One round-trip each for the per-project uniqueness flags and (insert only) the current
        # max version per key, instead of a query per contribution.
        unique_map = await self._projects.unique_identifiers_by_id(sorted({contributions[i].project for i in indices}))
        max_map: dict[tuple[str, str], int] = {}
        if not is_upsert:
            keys = sorted({(contributions[i].project, contributions[i].identifier) for i in indices})
            max_map = await self._contributions.max_versions(keys)

        seen: dict[tuple[str, str], int] = defaultdict(int)
        for i in indices:
            contrib = contributions[i]
            key = (contrib.project, contrib.identifier)

            if contrib.project not in unique_map:
                failures.append(
                    BulkFailure(
                        index=i,
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
                    version = 1
                elif contrib.version is not None:
                    version = contrib.version
                else:
                    failures.append(
                        BulkFailure(
                            index=i,
                            identifier=contrib.identifiers(),
                            error_code=ValidationError.error_code,
                            message=(
                                f"project '{contrib.project}' allows multiple versions; a 'version' "
                                "is required to identify which contribution to update"
                            ),
                        )
                    )
                    logger.info(
                        "ambiguous contribution version in project allowing multiple versions",
                        project=contrib.project,
                        identifiers=contrib.identifiers(),
                    )
                    continue
            elif unique:
                # Insert into a unique-identifier project: the first occurrence wins, anything that
                # already exists (in the DB or earlier in this batch) is a conflict.
                if key in max_map or seen[key] > 0:
                    failures.append(
                        BulkFailure(
                            index=i,
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

            plan.append(ResolvedWrite(index=i, contribution=contrib, version=version))
            seen[key] += 1

        return failures, plan

    def _split_oversize(
        self,
        indices: Iterable[int],
        contributions: list[ContributionIn],
    ) -> tuple[list[BulkFailure], list[int]]:
        """Reject contributions whose component count exceeds the per-contribution ceiling.

        Partitions ``indices`` into oversize ``BulkFailure`` entries and the remaining indices that
        should proceed to Mongo. Doing this upfront avoids burning a transaction slot on a request
        guaranteed to exceed transactionLifetimeLimitSeconds.
        """
        cap = self._settings.max_components_per_contribution
        oversize: list[BulkFailure] = []
        remaining: list[int] = []
        for i in indices:
            contrib = contributions[i]
            count = contrib.component_count()
            if count > cap:
                oversize.append(
                    BulkFailure(
                        index=i,
                        identifier=contrib.identifiers(),
                        error_code=ValidationError.error_code,
                        message=f"contribution has {count} components, exceeds cap of {cap}. "
                        "Recommend inserting the component alone, followed by bulk inserts of components",
                    )
                )
                logger.info("Attemped to add contribution with too many components.", num_components=count, max=cap)
            else:
                remaining.append(i)
        return oversize, remaining

    async def _split_contributions(
        self, contributions: list[ContributionIn], *, is_upsert: bool
    ) -> tuple[list[BulkFailure], list[ResolvedWrite]]:
        """Common method for validating contribution write failure logic and resolving versions.

        Runs the cheap, local, index-based filters first (authorization, then component-count cap)
        so guaranteed failures never reach the DB; ``_split_non_unique`` runs last and turns the
        remaining indices into a write plan carrying each resolved version.

        Returns:
            tuple of (failures and their reasons, a ``ResolvedWrite`` per contribution to write)
        """
        # Per-item project authorization (see _split_unauthorized for the per-item vs fail-fast
        # decision). Only authorized items reach Mongo; the rest are reported in ``failed``.
        unauthorized_failures, authorized_indices = self._split_unauthorized(range(len(contributions)), contributions)
        # Reject contributions that have too many components associated with them.
        oversize_failures, sized_indices = self._split_oversize(authorized_indices, contributions)
        # Verify identifiers/uniqueness within a project and resolve each version, depending on
        # project.unique_identifiers and whether this is an insert or upsert.
        non_unique_failures, plan = await self._split_non_unique(sized_indices, contributions, is_upsert=is_upsert)
        return (unauthorized_failures + oversize_failures + non_unique_failures, plan)

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
        """Per-contribution transaction path, bounded by ``max_concurrent_transactions``."""
        if not items:
            return [], []
        sem = asyncio.Semaphore(self._settings.max_concurrent_transactions)

        async def _bounded(item: ResolvedWrite) -> Contribution | BulkFailure:
            async with sem:
                return await self._insert_one_with_components(item)

        results = await asyncio.gather(*[_bounded(item) for item in items])
        succeeded: list[tuple[int, Contribution]] = []
        failed: list[BulkFailure] = []
        for item, outcome in zip(items, results, strict=True):
            if isinstance(outcome, BulkFailure):
                failed.append(outcome)
            else:
                succeeded.append((item.index, outcome))
        return succeeded, failed

    async def _insert_one_with_components(self, item: ResolvedWrite) -> Contribution | BulkFailure:
        """Run a single contribution + its components inside a transaction.

        Uses ``session.with_transaction`` so transient txn errors (write conflicts, primary step-
        downs) get pymongo's retry treatment. Any exception is converted to a ``BulkFailure`` so
        the surrounding ``asyncio.gather`` sees a normal return value for every coroutine.
        """
        contrib = item.contribution
        try:
            async with self._client.start_session() as session:

                async def _txn(s: AsyncClientSession) -> Contribution:
                    return await self._do_insert(contrib, s, item.version)

                return await session.with_transaction(_txn)
        except AppError as exc:
            return bulk_failure_from_exception(item.index, contrib.identifiers(), exc)
        except Exception as exc:
            logger.error(
                "insert_contribution_failed", index=item.index, identifier=contrib.identifiers(), exc_info=True
            )
            return bulk_failure_from_exception(item.index, contrib.identifiers(), exc)

    async def _do_insert(self, contrib: ContributionIn, session: AsyncClientSession, version: int) -> Contribution:
        """Insert components then the contribution itself, all in the given session.

        Components are inserted sequentially because a session is single-threaded — sharing it
        across concurrent awaits would corrupt the wire protocol.
        """
        structures = await self._structures.insert_components(contrib.structures or [], session=session)
        tables = await self._tables.insert_components(contrib.tables or [], session=session)

        doc = Contribution.from_input_model(contrib)
        doc.version = version
        doc.structures = cast(list[Link[Structure]] | None, structures or None)
        doc.tables = cast(list[Link[Table]] | None, tables or None)
        return await self._contributions.insert_contribution(doc, session=session)

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
            async with sem:
                try:
                    return await self._contributions.upsert_contribution_by_identifiers(
                        contrib.identifiers(), contrib, item.version
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
