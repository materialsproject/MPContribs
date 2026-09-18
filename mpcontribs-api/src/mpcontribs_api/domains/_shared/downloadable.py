import csv
import hashlib
import io
import json
from collections.abc import AsyncIterable, AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager
from typing import Any

from fastapi_filter.contrib.beanie import Filter
from types_aiobotocore_s3 import S3Client

from mpcontribs_api.domains._shared.models import BaseDocumentWithInput, DocumentOut
from mpcontribs_api.domains._shared.types import DownloadFormat
from mpcontribs_api.exceptions import DownloadError


class DownloadableRepository[TDoc: BaseDocumentWithInput, TOut: DocumentOut, TFilter: Filter]:
    """Mixin adding the download capability to a repository.

    The mixin makes no authorization decisions and owns no state. It borrows three attributes from
    its host repository, declared below as a dependency contract and resolved via MRO from
    :class:`MongoDbRepository`; the mixin never assigns them:

    - ``document_model``: the stored-document type, used to build the scoped query
    - ``out_model``: the output model each row is projected/validated into before serialization
    - ``_scope``: the user read scope injected into every query

    Mix it in before the base repository so its methods take precedence::

        class MongoDbContributionRepository(
            DownloadableRepository[Contribution, ContributionOut, ContributionFilter],
            MongoDbRepository[Contribution, ContributionIn, ContributionOut, ContributionFilter, ContributionPatch],
        ): ...
    """

    # Dependency contract — provided by the host repository via MRO, never assigned here.
    document_model: type[TDoc]
    out_model: type[TOut]
    _scope: dict[str, Any]

    def build_download_query(self, filter: TFilter) -> dict[str, Any]:
        """Return the effective Mongo query (caller filter AND user read scope) as a plain dict."""
        return filter.filter(self.document_model.find(self._scope)).get_filter_query()

    def _get_serializer(
        self, format: DownloadFormat, fields: frozenset[str] | None
    ) -> Callable[[AsyncIterable[TOut]], AsyncIterable[bytes]]:
        match format:
            case DownloadFormat.JSONL:
                return self._serialize_jsonl
            case DownloadFormat.CSV:
                return lambda rows: self._serialize_csv(rows, fields)
            case _:
                raise DownloadError("download format unhandled", format=format)

    @staticmethod
    async def _serialize_jsonl(rows: AsyncIterable) -> AsyncIterator[bytes]:
        async for out in rows:
            yield out.model_dump_json().encode() + b"\n"

    @staticmethod
    def _csv_cell(path: str, value: Any) -> dict[str, Any]:
        """Flatten one column's value to dotted-path leaves, keyed by their full path.

        A nested dict is descended into, prepending each key to ``path`` so
        ``{"v1": {"v2": {"v3": 1}}}`` at path ``"v1"`` yields ``{"v1.v2.v3": 1}``. Scalars terminate
        as a single cell; a list is JSON-encoded rather than exploded into index columns, as is an
        empty dict (it has no leaf to flatten).
        """
        if isinstance(value, dict) and value:
            flat: dict[str, Any] = {}
            for key, sub in value.items():
                flat |= DownloadableRepository._csv_cell(f"{path}.{key}", sub)
            return flat
        if value is None or isinstance(value, (str, int, float, bool)):
            return {path: value}
        return {path: json.dumps(value, ensure_ascii=False, separators=(",", ":"))}

    @staticmethod
    async def _serialize_csv(rows: AsyncIterable, fields: frozenset[str] | None) -> AsyncIterator[bytes]:
        buf = io.StringIO()
        writer: csv.DictWriter | None = None
        async for out in rows:
            # Flatten each top-level column so nested dicts become dotted-path columns.
            row: dict[str, Any] = {}
            for key, value in out.model_dump(mode="json").items():
                row |= DownloadableRepository._csv_cell(str(key), value)
            if writer is None:
                cols = sorted(fields) if fields else list(row.keys())
                writer = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
                writer.writeheader()
            writer.writerow(row)
            yield buf.getvalue().encode()
            buf.seek(0)
            buf.truncate(0)

    def _hash_payload(self, payload: dict[str, Any], *, separators: tuple[str, str] = (",", ":")) -> str:
        canonical: str = json.dumps(
            obj=payload,
            sort_keys=True,
            separators=separators,
            ensure_ascii=True,
            default=str,  # filters may carry ObjectId/datetime values; stringify for a stable key
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    async def _s3_object_exists(self, bucket_name: str, key_name: str, s3: AbstractAsyncContextManager[S3Client]):
        async with s3 as s3_client:
            try:
                await s3_client.head_object(Bucket=bucket_name, Key=key_name)
                return True
            except Exception:
                return False
