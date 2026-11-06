from collections.abc import AsyncIterable
from contextlib import AbstractAsyncContextManager
from itertools import permutations
from typing import Any

from pymatgen.core import Composition
from pymatgen.core.composition import CompositionError
from types_aiobotocore_s3 import S3Client

from mpcontribs_api.domains._shared.types import DownloadFormat, ShortMimeFormat
from mpcontribs_api.domains.contributions.models import ContributionFilter, ContributionOut
from mpcontribs_api.domains.contributions.repository import MongoDbContributionRepository
from mpcontribs_api.exceptions import ValidationError
from mpcontribs_api.pagination import CursorParams, Page


class ContributionService:
    """Read-only access service for contributions.

    Contributions are worker-written S3-backed documents: creation, replacement, and deletion all
    flow through the ``/uploads`` endpoints, so this service exposes reads only — fetch, list, a
    streaming export, and formula search.
    """

    def __init__(self, contributions: MongoDbContributionRepository):
        self._contributions = contributions

    async def read_one(self, identifiers: dict[str, Any], fields: frozenset[str] | None) -> ContributionOut | None:
        """Return the single scoped contribution matching ``identifiers``, or None when none matches.

        Accepts either the bare ``{"id": ...}`` form or the semantic
        ``{"project", "identifier", "version"}`` set, resolved by the base ``_identifier_query``.
        An ambiguous natural identity raises ``ConflictError``.
        """
        return await self._contributions.read_one(identifiers, fields)

    async def read_many(
        self, pagination: CursorParams, filter: ContributionFilter, fields: frozenset[str] | None
    ) -> Page[ContributionOut]:
        return await self._contributions.read_many(pagination=pagination, filter=filter, fields=fields)

    async def download(
        self,
        format: DownloadFormat,
        short_mime: ShortMimeFormat,
        ignore_cache: bool,
        filter: ContributionFilter,
        fields: frozenset[str] | None,
        s3: AbstractAsyncContextManager[S3Client],
    ) -> AsyncIterable[bytes]:
        """Stream a gzip-compressed export of matching contributions. See repository ``download``."""
        return self._contributions.download(
            format=format,
            short_mime=short_mime,
            ignore_cache=ignore_cache,
            filter=filter,
            fields=fields,
            s3=s3,
            key_name="",  # TODO: Temp
            bucket_name="contributions",
        )

    async def search(self, query: str, limit: int = 10) -> list[ContributionOut]:
        if not query:
            raise ValidationError(message="search query cannot be empty")
        try:
            comp = Composition(query)
        except (CompositionError, ValueError) as err:
            raise ValidationError(message="invalid formula provided", formula=query) from err

        # Guard against explosion of permutations
        # TODO: Remove once proper SearchIndex Analyzer is used
        if len(comp.elements) > 5:
            raise ValidationError(message="too many elements in search formula", query=query)
        # Build the element-count permutations to match against the formula index.
        # NOTE: This block could probably be replaced by a MongoDB Analyzer.
        # then we should include "matchCriteria: all" so when tokenizing a formula, all tokens are required
        # This prevents query=Fe2O3 from returning documents like AlO3 (O3 token match)
        ind_str = []
        if len(comp) == 1:
            d = comp.get_integer_formula_and_factor()
            ind_str.append(d[0] + str(int(d[1])) if d[1] != 1 else d[0])
        else:
            for i, j in comp.reduced_composition.items():
                ind_str.append(i.name + str(int(j)) if j != 1 else i.name)
        final_terms = ["".join(entry) for entry in permutations(ind_str)]

        return await self._contributions.search(final_terms, limit)
