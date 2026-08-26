from collections.abc import Callable, Collection
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from mpcontribs_api.authz import User


@runtime_checkable
class ScopeClause(Protocol):
    """One term of a read-visibility rule.

    Returns the MongoDB fragment that grants visibility to ``user`` under this clause, or ``None``
    when the clause does not apply (e.g. an owner clause for an anonymous caller). Returning ``None``
    drops the clause from the ``$or`` rather than contributing a match-nothing term.
    """

    def to_query(self, user: User) -> dict[str, Any] | None: ...


@dataclass(frozen=True)
class Public:
    """Visibility of released data: public (optionally also approved) documents.

    Always applies — public documents are visible to every caller, including anonymous ones — so this
    is the baseline clause every scoped collection includes.
    """

    approved: bool = False

    def to_query(self, user: User) -> dict[str, Any]:
        if self.approved:
            return {"is_public": True, "is_approved": True}
        return {"is_public": True}


@dataclass(frozen=True)
class Owned:
    """Visibility of the caller's own documents, keyed on an owner field.

    Inapplicable to anonymous callers: ``{owner: None}`` would wrongly match owner-less documents, so
    the clause is dropped rather than emitted.
    """

    field: str = "owner"

    def to_query(self, user: User) -> dict[str, Any] | None:
        if user.is_anonymous:
            return None
        return {self.field: user.username}


@dataclass(frozen=True)
class RoleIn:
    """Visibility granted by the caller's roles, as a ``{field: {"$in": [...]}}`` membership test.

    ``source`` is the ``User`` atrtribute holding the granted ids (ie. ``"project_groups"``). Any role
    assignment grants readability.
    """

    field: str
    source: str
    # TODO: Remove once _id -> PydanticObjectId coercion handling is improved
    coerce: Callable[[Any], Any] | None = None

    def to_query(self, user: User) -> dict[str, Any] | None:
        raw: Collection[Any] = getattr(user, self.source)
        values = self._coerce(raw)
        if not values:
            return None
        return {self.field: {"$in": sorted(values)}}

    def _coerce(self, raw: Collection[Any]) -> list[Any]:
        if self.coerce is None:
            return list(raw)
        out: list[Any] = []
        for value in raw:
            try:
                out.append(self.coerce(value))
            except Exception:
                # Fail-closed: a role value that cannot be coerced to the id type is not a grant.
                continue
        return out


class Scope:
    """A collection's read-visibility rule as a composition of :class:`ScopeClause` terms.

    :meth:`query` turns a ``User`` into the MongoDB filter injected into every scoped read. Admins
    bypass read scope everywhere (a global rule, matching ``User.is_admin``). A ``Scope`` with no
    clauses filters nothing — the explicit "unscoped collection" case (components, consumers), whose
    visibility is gated elsewhere or not at all.
    """

    def __init__(self, *clauses: ScopeClause) -> None:
        self.clauses: tuple[ScopeClause, ...] = clauses

    def query(self, user: User) -> dict[str, Any]:
        if user.is_admin:
            return {}
        ors = [fragment for clause in self.clauses if (fragment := clause.to_query(user)) is not None]
        return {"$or": ors} if ors else {}
