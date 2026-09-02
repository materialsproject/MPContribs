from collections.abc import Iterator
from typing import Any

from mpcontribs_api.domains._shared.repository import MongoDbRepository
from mpcontribs_api.domains.consumers.models import (
    Consumer,
    ConsumerFilter,
    ConsumerIn,
    ConsumerOut,
    ConsumerPatch,
)
from mpcontribs_api.scope import Scope


def _flatten(prefix: str, value: dict[str, Any]) -> Iterator[tuple[str, Any]]:
    """Yield ``(dotted_key, leaf_value)`` for every leaf in a nested settings dict.

    Recurses into nested dicts so a patch of ``{"contribution": {"max_components": 1}}`` under the
    ``settings`` prefix becomes ``settings.contribution.max_components``, leaving sibling leaves and
    sibling domains untouched.
    """
    for key, sub in value.items():
        dotted = f"{prefix}.{key}"
        if isinstance(sub, dict):
            yield from _flatten(dotted, sub)
        else:
            yield dotted, sub


class MongoDbConsumerRepository(MongoDbRepository[Consumer, ConsumerIn, ConsumerOut, ConsumerFilter, ConsumerPatch]):
    """Repository for admin-managed consumer overrides.

    Consumer overrides are an admin-only resource: every route that reaches this repository is
    gated by ``require_admin``, so no per-user read scope is needed and ``read_scope`` is
    unrestricted (admins see all overrides). Only the nested-``settings`` patch shape is resource-specific.
    """

    document_model = Consumer
    out_model = ConsumerOut
    # Admin-only resource (routes enforce ``require_admin``); no clauses → no visibility filter.
    read_scope = Scope()

    def _update_fields(self, update: ConsumerPatch) -> dict[str, Any]:
        """Flatten the patch to dotted ``settings.<domain>.<leaf>`` keys.

        The limits live under a nested, domain-grouped ``settings`` sub-document; dotting the update
        down to each leaf makes a partial patch change only the named limits and leave the siblings
        intact (a plain ``$set`` of ``settings`` — or of ``settings.<domain>`` — would replace the
        whole sub-document).
        """
        overrides = update.settings.model_dump(exclude_unset=True) if update.settings else {}
        return dict(_flatten("settings", overrides))
