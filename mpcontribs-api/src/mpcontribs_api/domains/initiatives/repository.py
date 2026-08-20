from mpcontribs_api.domains._shared.repository import MongoDbRepository
from mpcontribs_api.domains.initiatives.models import (
    Initiative,
    InitiativeFilter,
    InitiativeIn,
    InitiativeOut,
    InitiativePatch,
)
from mpcontribs_api.scope import Owned, Public, RoleIn, Scope


class MongoDbInitiativeRepository(
    MongoDbRepository[Initiative, InitiativeIn, InitiativeOut, InitiativeFilter, InitiativePatch]
):
    """Query/persistence toolbox for initiatives."""

    document_model = Initiative
    out_model = InitiativeOut
    # Visible when public+approved, owned by the caller, or collaborated on via an
    # ``initiative:<slug>`` role (keyed on ``slug``). Admins bypass scope (handled by ``Scope``).
    read_scope = Scope(Public(approved=True), Owned(), RoleIn("slug", "initiative_roles"))

    async def count_unapproved_for_owner(self, owner: str) -> int:
        """Count ``owner``'s unapproved initiatives, ignoring user scope."""
        return await self.document_model.find(
            self.document_model.owner == owner,
            self.document_model.is_approved == False,  # noqa: E712 — Beanie needs the value, not `is`
        ).count()
