from typing import Any

from fastapi_filter.contrib.beanie import Filter

from mpcontribs_api.domains._shared.models import BaseDocumentWithInput, DocumentOut


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
