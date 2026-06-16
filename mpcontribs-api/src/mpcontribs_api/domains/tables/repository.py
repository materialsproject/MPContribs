from collections.abc import AsyncIterable
from contextlib import AbstractAsyncContextManager

from pymongo.asynchronous.client_session import AsyncClientSession
from types_aiobotocore_s3 import S3Client

from mpcontribs_api.domains._shared.components import MongoDbComponentsRepository
from mpcontribs_api.domains._shared.models import DeleteResponse
from mpcontribs_api.domains._shared.types import DownloadFormat, ShortMimeFormat
from mpcontribs_api.domains.tables.models import (
    Table,
    TableFilter,
    TableIn,
    TableOut,
    TablePatch,
)
from mpcontribs_api.pagination import CursorParams, Page


class MongoDbTableRepository(MongoDbComponentsRepository[Table, TableIn, TableOut, TableFilter, TablePatch]):
    document_model = Table
    out_model = TableOut

    async def insert_tables(
        self,
        tables: list[TableIn],
        session: AsyncClientSession | None = None,
    ) -> list[Table]:
        """Bulk-insert tables, chunked to fit within a transaction's payload budget.

        Args:
            tables: tables to insert
            session: optional client session; pass when inserTableIng inside a transaction
        """
        return await self.insert_components(components=tables, session=session)

    async def insert_table(self, table: TableIn) -> Table:
        """Insert a single table.

        Args:
            table (TableIn): the table to insert

        Returns:
            TDpc: the table actually in the database

        Raises:
            AppError: If insert_one returns None, raises
        """
        return await self.insert_component(component=table)

    async def get_tables(
        self,
        filter: TableFilter,
        pagination: CursorParams,
        fields: frozenset[str] | None,
    ) -> Page[TableOut]:
        """Query the table collection, scoped to the current user. See ``get_many``."""
        return await self.get_many(pagination=pagination, filter=filter, fields=fields)

    async def get_table_by_id(self, id: str, fields: frozenset[str] | None) -> Table | TableOut | None:
        """Find a single table by id, scoped to the current user. See ``get_by_id``."""
        return await self.get_component_by_id(id, fields)

    async def download_tables(
        self,
        format: DownloadFormat,
        short_mime: ShortMimeFormat,
        ignore_cache: bool,
        filter: TableFilter,
        fields: frozenset[str] | None,
        s3: AbstractAsyncContextManager[S3Client],
        bucket_name: str,
        key_name: str,
    ) -> AsyncIterable[bytes]:
        return self.download(
            format=format,
            short_mime=short_mime,
            ignore_cache=ignore_cache,
            filter=filter,
            fields=fields,
            s3=s3,
            bucket_name=bucket_name,
            key_name=key_name,
        )

    async def delete_tables(
        self,
        filter: TableFilter,
        session: AsyncClientSession | None = None,
    ) -> DeleteResponse:
        """Deletes all tables matching ``filter``.

        Args:
            filter (TableFilter): the query to filter tables by
            session (AsyncClientSession | None): the current session, used to guarantee transactions

        Returns:
            DeleteResponse: A report of the deletion
        """
        return await self.delete_components(filter=filter, session=session)

    async def delete_table_by_id(
        self,
        id: str,
        session: AsyncClientSession | None = None,
    ) -> DeleteResponse:
        """Deletes a single table by Id.

        Args:
            id (str): the str representation of the table's ObjectId
            session (AsyncClientSession | None): the current session, used to guarantee transactions

        Returns:
            DeleteResponse: A report of the deletion
        """
        return await self.delete_component_by_id(id=id, session=session)

    async def patch_table_by_id(self, id: str, update: TablePatch) -> Table:
        """Partially update a table by id, scoped to the current user. See ``patch``."""
        return await self.patch_component_by_id(id=id, update=update)
