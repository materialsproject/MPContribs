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
