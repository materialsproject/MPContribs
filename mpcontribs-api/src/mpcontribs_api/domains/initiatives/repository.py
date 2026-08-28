from mpcontribs_api.authz import INITIATIVE_PATH
from mpcontribs_api.domains._shared.repository import MongoDbRepository
from mpcontribs_api.domains.initiatives.models import (
    Initiative,
    InitiativeFilter,
    InitiativeIn,
    InitiativeOut,
    InitiativePatch,
)
from mpcontribs_api.scope import Granted, Owned, Public, Scope


class MongoDbInitiativeRepository(
    MongoDbRepository[Initiative, InitiativeIn, InitiativeOut, InitiativeFilter, InitiativePatch]
):
    """Query/persistence toolbox for initiatives."""

    document_model = Initiative
    out_model = InitiativeOut
    # Visible when public+approved, owned by the caller, or granted any role on the initiative via a
    # ``mpcontribs:initiatives/<slug>=<role>`` grant (keyed on ``slug``). Admins bypass scope.
    read_scope = Scope(Public(approved=True), Owned(), Granted("slug", INITIATIVE_PATH))
