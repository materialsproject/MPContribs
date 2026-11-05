from fastapi_filter.contrib.beanie import Filter
from pydantic import BaseModel

from mpcontribs_api.domains._shared.models import DocumentOut
from mpcontribs_api.domains._shared.repository import MongoDbRepository
from mpcontribs_api.domains.components.models import Component
from mpcontribs_api.scope import Scope


class MongoDbComponentsRepository[TDoc: Component, TOut: DocumentOut, TFilter: Filter](
    MongoDbRepository[TDoc, BaseModel, TOut, TFilter, BaseModel]
):
    """Base repository for the thin, content-addressed component index collections.

    Component data is stored in S3. This Repository only serves to read metadata stored in MongoDB collections.
    All modifying operations must take place through the `/uploads` domain.

    ``TIn``/``TPatch`` are bound to ``BaseModel`` because there is no input/patch contract.
    """

    read_scope = Scope()
