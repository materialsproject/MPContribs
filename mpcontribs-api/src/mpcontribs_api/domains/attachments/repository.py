from collections.abc import AsyncIterable

from pymongo.asynchronous.client_session import AsyncClientSession

from mpcontribs_api.domains._shared.components import MongoDbComponentsRepository
from mpcontribs_api.domains._shared.models import DeleteResponse
from mpcontribs_api.domains._shared.types import DownloadFormat, ShortMimeFormat
from mpcontribs_api.domains.attachments.models import (
    Attachment,
    AttachmentFilter,
    AttachmentIn,
    AttachmentOut,
    AttachmentPatch,
)
from mpcontribs_api.pagination import CursorParams, Page


class MongoDbAttachmentRepository(
    MongoDbComponentsRepository[Attachment, AttachmentIn, AttachmentOut, AttachmentFilter, AttachmentPatch]
):
    document_model = Attachment
    out_model = AttachmentOut

    async def get_attachments(
        self,
        filter: AttachmentFilter,
        pagination: CursorParams,
        fields: frozenset[str] | None,
    ) -> Page[AttachmentOut]:
        """Query the attachment collection, scoped to the current user. See ``get_many``."""
        return await self.get_many(pagination=pagination, filter=filter, fields=fields)

    async def get_attachment_by_id(self, id: str, fields: frozenset[str] | None) -> Attachment | AttachmentOut | None:
        """Find a single table by id, scoped to the current user. See ``get_by_id``."""
        return await self.get_component_by_id(id, fields)

    async def download_attachments(
        self,
        format: DownloadFormat,
        short_mime: ShortMimeFormat,
        ignore_cache: bool,
        filter: AttachmentFilter,
        fields: frozenset[str] | None,
    ) -> AsyncIterable[bytes]:
        return self.download(
            format=format,
            short_mime=short_mime,
            ignore_cache=ignore_cache,
            filter=filter,
            fields=fields,
        )

    async def delete_attachments(
        self,
        filter: AttachmentFilter,
        session: AsyncClientSession | None = None,
    ) -> DeleteResponse:
        """Deletes all attachments matching ``filter``.

        Args:
            filter (AttachmentFilter): the query to filter attachments by
            session (AsyncClientSession | None): the current session, used to guarantee transactions

        Returns:
            DeleteResponse: A report of the deletion
        """
        return await self.delete_components(filter=filter, session=session)

    async def delete_attachment_by_id(
        self,
        id: str,
        session: AsyncClientSession | None = None,
    ) -> DeleteResponse:
        """Deletes a single attachment by Id.

        Args:
            id (str): the str representation of the attachment's ObjectId
            session (AsyncClientSession | None): the current session, used to guarantee transactions

        Returns:
            DeleteResponse: A report of the deletion
        """
        return await self.delete_component_by_id(id=id, session=session)
