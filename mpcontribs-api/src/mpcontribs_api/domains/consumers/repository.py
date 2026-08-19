from typing import Any

from mpcontribs_api.authz import User
from mpcontribs_api.domains._shared.repository import MongoDbRepository
from mpcontribs_api.domains.consumers.models import (
    Consumer,
    ConsumerFilter,
    ConsumerIn,
    ConsumerOut,
    ConsumerPatch,
)


class MongoDbConsumerRepository(MongoDbRepository[Consumer, ConsumerIn, ConsumerOut, ConsumerFilter, ConsumerPatch]):
    """Repository for admin-managed consumer overrides.

    Consumer overrides are an admin-only resource: every route that reaches this repository is
    gated by ``require_admin``, so no per-user read scope is needed and ``_build_scope`` returns an
    empty filter (admins see all overrides). Reads and deletes use the base repository directly
    (keyed on ``consumer_id`` via ``Consumer.identifier_fields``); only the nested-``settings`` patch
    shape is resource-specific.
    """

    document_model = Consumer
    out_model = ConsumerOut

    @staticmethod
    def _build_scope(user: User) -> dict[str, Any]:
        # Admin-only resource (routes enforce ``require_admin``); no visibility filter required.
        return {}

    def _patch_update_fields(self, update: ConsumerPatch) -> dict[str, Any]:
        """Flatten the patch to dotted ``settings.<field>`` keys.

        The limits live under a nested ``settings`` sub-document; dotting the update makes a partial
        patch change only the named limits and leave the siblings intact (a plain ``$set`` of
        ``settings`` would replace the whole sub-document).
        """
        overrides = update.settings.model_dump(exclude_unset=True) if update.settings else {}
        return {f"settings.{field}": value for field, value in overrides.items()}
