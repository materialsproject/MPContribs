from collections.abc import Iterable
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
    levels: Iterable[tuple[DownloadDomain, DownloadableRepository[Any, Any, Any], Filter | None]],
) -> dict[str, list[dict[str, Any]]]:
    """Assemble the ``{collection_name: [scoped_query]}`` map for a bundled download.

    Each ``(collection, repository, filter)`` level whose ``filter`` is set contributes one scoped
    predicate (``repository.build_download_query(filter)``) under its collection name; levels whose
    filter is ``None`` are omitted. The worker treats the topmost collection present as the root and
    joins the remaining (descendant) collections from it.
    """
    return {
        domain.value: [repository.build_download_query(filter)]
        for domain, repository, filter in levels
        if filter is not None
    }
