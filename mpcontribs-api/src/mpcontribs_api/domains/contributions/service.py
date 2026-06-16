import asyncio
from collections import defaultdict
from typing import cast

import structlog
from beanie import Link, PydanticObjectId
from pymongo import AsyncMongoClient
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import BulkWriteError

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
from mpcontribs_api.domains.structures.models import Structure
from mpcontribs_api.domains.structures.repository import MongoDbStructureRepository
from mpcontribs_api.domains.tables.models import Table
from mpcontribs_api.domains.tables.repository import MongoDbTableRepository
from mpcontribs_api.exceptions import AppError, ValidationError
from mpcontribs_api.pagination import CursorParams

logger = structlog.get_logger(__name__)


class ContributionService:
    def __init__(
        self,
        client: AsyncMongoClient,
        contributions: MongoDbContributionRepository,
        structures: MongoDbStructureRepository,
        attachments: MongoDbAttachmentRepository,
        tables: MongoDbTableRepository,
        settings: MongoSettings | None = None,
    ):
        self._client = client
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

        Args:
            contributions: contributions to insert; may include nested structures/tables/attachments

        Returns:
            BulkWriteSummary[Contribution]: per-item outcome, sized to ``len(contributions)``

        Raises:
            ValidationError: if duplicate keys (project-identifier) are found in ``contributions``
        """
        if not contributions:
            return BulkWriteSummary[Contribution](total=0, succeeded=[], failed=[])

        self._reject_duplicate_keys(contributions)

        oversize_failures, remaining_indices = self._split_oversize(contributions)
        no_comp_indices = [i for i in remaining_indices if not contributions[i].has_components()]
        with_comp_indices = [i for i in remaining_indices if contributions[i].has_components()]

        no_comp_succeeded, no_comp_failed = await self._insert_no_components(
            indices=no_comp_indices,
            contributions=contributions,
        )
        with_comp_succeeded, with_comp_failed = await self._insert_with_components(
            indices=with_comp_indices,
            contributions=contributions,
        )

        succeeded = [doc for _, doc in sorted(no_comp_succeeded + with_comp_succeeded, key=lambda p: p[0])]
        failed = sorted(
            oversize_failures + no_comp_failed + with_comp_failed,
            key=lambda f: f.index,
        )
        return BulkWriteSummary[Contribution](total=len(contributions), succeeded=succeeded, failed=failed)

    def _reject_duplicate_keys(self, contributions: list[ContributionIn]) -> None:
        """Reject the whole batch if any identifying key appears more than once.

        Mongo would surface this as a duplicate key error; catching it upfront keeps a guaranteed
        failure from consuming a transaction slot and gives the caller all offending indices at once.

        The dedup key is derived from every value in ``identifiers()`` so adding a field to the
        uniqueness contract there flows through here automatically.
        """
        seen: dict[tuple[str, ...], list[int]] = defaultdict(list)
        for index, contribution in enumerate(contributions):
            ids = contribution.identifiers()
            seen[tuple(ids.values())].append(index)
        duplicates = sorted(index for indices in seen.values() if len(indices) > 1 for index in indices)
        if duplicates:
            raise ValidationError(
                "Duplicate (project, identifier) pairs in batch",
                contribution_indices=duplicates,
            )

    def _split_oversize(self, contributions: list[ContributionIn]) -> tuple[list[BulkFailure], list[int]]:
        """Reject contributions whose component count exceeds the per-contribution ceiling.

        Returns the failure entries for the oversize items and the indices of the remaining items
        that should proceed to Mongo. Doing this upfront avoids burning a transaction slot on a
        request guaranteed to exceed transactionLifetimeLimitSeconds.
        """
        cap = self._settings.max_components_per_contribution
        oversize: list[BulkFailure] = []
        remaining: list[int] = []
        for i, contrib in enumerate(contributions):
            count = contrib.component_count()
            if count > cap:
                oversize.append(
                    BulkFailure(
                        index=i,
                        identifier=contrib.identifiers(),
                        error_code="validation_error",
                        message=f"contribution has {count} components, exceeds cap of {cap}. "
                        "Recommend inserting the component alone, followed by bulk inserts of components",
                    )
                )
            else:
                remaining.append(i)
        return oversize, remaining

    async def _insert_no_components(
        self,
        indices: list[int],
        contributions: list[ContributionIn],
    ) -> tuple[list[tuple[int, Contribution]], list[BulkFailure]]:
        """Single-collection bulk insert for component-free contributions.

        Uses ``ordered=False`` so a single bad item doesn't sink the rest of the batch. pymongo
        raises ``BulkWriteError`` with per-index error info on partial failure; we map that back
        onto the original input indices.
        """
        if not indices:
            return [], []
        docs = [Contribution.from_input_model(contributions[i]) for i in indices]
        try:
            await self._contributions.insert_many_contributions(docs)
            return list(zip(indices, docs, strict=False)), []
        except BulkWriteError as exc:
            return self._partition_bulk_write_error(indices, docs, contributions, exc)

    @staticmethod
    def _partition_bulk_write_error(
        indices: list[int],
        docs: list[Contribution],
        contributions: list[ContributionIn],
        exc: BulkWriteError,
    ) -> tuple[list[tuple[int, Contribution]], list[BulkFailure]]:
        """Map pymongo's per-position writeErrors back to the caller's original input indices."""
        write_errors = exc.details.get("writeErrors", []) if exc.details else []
        failed_positions = {err.get("index"): err for err in write_errors}
        succeeded: list[tuple[int, Contribution]] = []
        failed: list[BulkFailure] = []
        for position, (orig_index, doc) in enumerate(zip(indices, docs, strict=False)):
            err = failed_positions.get(position)
            if err is None:
                succeeded.append((orig_index, doc))
            else:
                failed.append(
                    BulkFailure(
                        index=orig_index,
                        identifier=contributions[orig_index].identifiers(),
                        error_code="conflict" if err.get("code") == 11000 else "write_error",
                        message=err.get("errmsg", "write failed"),
                    )
                )
        return succeeded, failed

    async def _insert_with_components(
        self,
        indices: list[int],
        contributions: list[ContributionIn],
    ) -> tuple[list[tuple[int, Contribution]], list[BulkFailure]]:
        """Per-contribution transaction path, bounded by ``max_concurrent_transactions``."""
        if not indices:
            return [], []
        sem = asyncio.Semaphore(self._settings.max_concurrent_transactions)

        async def _bounded(orig_index: int) -> Contribution | BulkFailure:
            async with sem:
                return await self._insert_one_with_components(orig_index, contributions[orig_index])

        results = await asyncio.gather(*[_bounded(i) for i in indices])
        succeeded: list[tuple[int, Contribution]] = []
        failed: list[BulkFailure] = []
        for orig_index, outcome in zip(indices, results, strict=True):
            if isinstance(outcome, BulkFailure):
                failed.append(outcome)
            else:
                succeeded.append((orig_index, outcome))
        return succeeded, failed

    async def _insert_one_with_components(
        self,
        index: int,
        contrib: ContributionIn,
    ) -> Contribution | BulkFailure:
        """Run a single contribution + its components inside a transaction.

        Uses ``session.with_transaction`` so transient txn errors (write conflicts, primary step-
        downs) get pymongo's retry treatment. Any exception is converted to a ``BulkFailure`` so
        the surrounding ``asyncio.gather`` sees a normal return value for every coroutine.
        """
        try:
            async with self._client.start_session() as session:

                async def _txn(s: AsyncClientSession) -> Contribution:
                    return await self._do_insert(contrib, s)

                return await session.with_transaction(_txn)
        except AppError as exc:
            return bulk_failure_from_exception(index, contrib.identifiers(), exc)
        except Exception as exc:
            logger.error("insert_contribution_failed", index=index, identifier=contrib.identifiers(), exc_info=True)
            return bulk_failure_from_exception(index, contrib.identifiers(), exc)

    async def _do_insert(self, contrib: ContributionIn, session: AsyncClientSession) -> Contribution:
        """Insert components then the contribution itself, all in the given session.

        Components are inserted sequentially because a session is single-threaded — sharing it
        across concurrent awaits would corrupt the wire protocol.
        """
        structures = await self._structures.insert_structures(contrib.structures or [], session=session)
        tables = await self._tables.insert_tables(contrib.tables or [], session=session)

        doc = Contribution.from_input_model(contrib)
        doc.structures = cast(list[Link[Structure]] | None, structures or None)
        doc.tables = cast(list[Link[Table]] | None, tables or None)
        return await self._contributions.insert_contribution(doc, session=session)

    async def upsert_contributions(self, contributions: list[ContributionIn]) -> list[Contribution]:
        """Upsert contributions by their identifying fields, bounded by concurrency caps.

        Components (structures, tables, attachments) must be managed via their respective
        services. If any contribution in the batch carries components, the entire request is
        rejected before any database writes occur.

        Each item is upserted atomically by ``ContributionIn.identifiers()`` via a single
        ``findOneAndUpdate(..., upsert=True)`` so two requests targeting the same key cannot
        race past the find branch — the unique index over those fields is the tiebreaker.
        Concurrent upserts within a batch are bounded by ``settings.mongo.max_concurrent_transactions``

        Args:
            contributions: contributions to upsert; must not include nested components

        Returns:
            list[Contribution]: upserted documents in input order
        """
        indices_with_components = [i for i, c in enumerate(contributions) if c.has_components()]
        if indices_with_components:
            raise ValidationError(
                "Components must be managed via their respective services, not via contribution upsert.",
                contribution_indices=indices_with_components,
            )

        sem = asyncio.Semaphore(self._settings.max_concurrent_transactions)

        async def _bounded_upsert(contrib: ContributionIn) -> Contribution:
            async with sem:
                return await self._contributions.upsert_contribution_by_identifiers(contrib.identifiers(), contrib)

        return await asyncio.gather(*[_bounded_upsert(c) for c in contributions])

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
                ids = [link.ref.id for c in page.items for link in getattr(c, field)]
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
