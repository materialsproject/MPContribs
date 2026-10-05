from collections.abc import Collection, Iterable
from typing import Any

from fastapi_filter.contrib.beanie import Filter

from mpcontribs_api.domains._shared.models import BaseDocumentWithInput, DocumentOut
from mpcontribs_api.domains.downloads.models import DownloadDomain


class DownloadableRepository[TDoc: BaseDocumentWithInput, TOut: DocumentOut, TFilter: Filter]:
    """Mixin adding the download capability to a repository.


    - ``document_model``: the stored-document type, used to build the scoped query
    - ``_scope``: the user read scope injected into every query

    Mix it in before the base repository so its methods take precedence::

        class MongoDbContributionRepository(
            DownloadableRepository[Contribution, ContributionOut, ContributionFilter],
            MongoDbRepository[Contribution, ContributionIn, ContributionOut, ContributionFilter, ContributionPatch],
        ): ...
    """

    # Dependency contract — provided by the host repository via MRO, never assigned here.
    document_model: type[TDoc]
    _scope: dict[str, Any]

    def build_download_query(self, filter: TFilter) -> dict[str, Any]:
        """Return the effective Mongo query (caller filter AND user read scope) as a plain dict."""
        return filter.filter(self.document_model.find(self._scope)).get_filter_query()


def build_query_map(
    levels: Iterable[
        tuple[DownloadDomain, DownloadableRepository[Any, Any, Any], Filter | None, Collection[Any] | None]
    ],
) -> dict[str, list[dict[str, Any]]]:
    """Build the ``{collection_name: [query]}`` map for a bundled download.

    Each level in `levels` with a set ``filter`` adds one scoped query under its collection name; filters set to
    ``None`` are skipped. ``gate_ids`` (the last element of the tuple) restricts components (which have no read scope of
    their own) to the ids reachable in the caller's scope, ANDing ``{"_id": {"$in": sorted(gate_ids)}}`` onto the query;
    self-scoping roots (projects/contributions) pass ``None``.
    """
    out: dict[str, list[dict[str, Any]]] = {}
    for domain, repository, filter, gate_ids in levels:
        if filter is None:
            continue
        base = repository.build_download_query(filter)
        predicate = base if gate_ids is None else {"$and": [base, {"_id": {"$in": sorted(gate_ids)}}]}
        out[domain.value] = [predicate]
    return out
