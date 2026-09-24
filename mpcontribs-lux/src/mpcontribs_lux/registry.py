from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Callable, ClassVar, Protocol, cast

from pydantic import BaseModel


def _schema_name(schema: str | type[BaseModel]) -> str:
    """Normalize a schema reference (class or name) to its registered name."""
    return schema if isinstance(schema, str) else schema.__name__


class ValidatedTables:
    """A submission's attached tables, already validated into their models.

    Look rows up *by their schema class* so the concrete row type flows to the
    call site through a generic ``TypeVar`` - ``tables.rows(Cluster)`` is
    statically ``list[Cluster]``
    """

    def __init__(self, by_name: dict[str, list[BaseModel]]) -> None:
        self._by_name: dict[str, list[BaseModel]] = by_name

    def rows[M: BaseModel](self, schema: type[M]) -> list[M]:
        """Return the validated rows for ``schema``.

        Raises ``KeyError`` (with the schema name) when that table was not part
        of the submission.
        """
        return cast(list[M], self._by_name[schema.__name__])

    def get[M: BaseModel](self, schema: type[M]) -> list[M] | None:
        """Return the validated rows for ``schema``, or ``None`` if not submitted."""
        validated = self._by_name.get(schema.__name__)
        if validated is None:
            return None
        return cast(list[M], validated)

    def names(self) -> frozenset[str]:
        """Return the set of submitted table schema names."""
        return frozenset(self._by_name)

    def __contains__(self, schema: type[BaseModel] | str) -> bool:
        return _schema_name(schema) in self._by_name

    def __iter__(self):
        return iter(self._by_name)

    def __len__(self) -> int:
        return len(self._by_name)


class Validator(Protocol):
    """A cross-object validator expressing an invariant pydantic cannot.

    It runs after :meth:`LuxRegistry.validate` has already validated the
    contribution and every attached table row against their schemas, so it
    receives the validated contribution model, the attached tables as a
    :class:`ValidatedTables`, and any structures as ``{structure_name: record}``.
    It asserts a contribution<->table or table<->table invariant or raises on a violation.
    """

    def __call__(
        self,
        contribution: Any,
        tables: ValidatedTables,
        structures: dict[str, Any],
        /,
    ) -> None: ...


@dataclass(frozen=True)
class _RegisteredValidator:
    """A validator plus the submission shape that triggers it.

    ``contribution`` (a contribution schema name) and ``tables`` (table schema
    names that must all be present) are the gates; at least one is always set.
    """

    func: Validator
    contribution: str | None
    tables: tuple[str, ...]

    def applies_to(
        self, contribution_name: str, present_tables: frozenset[str]
    ) -> bool:
        """True when this submission's contribution/tables match the gates."""
        if self.contribution is not None and self.contribution != contribution_name:
            return False
        return present_tables.issuperset(self.tables)


class SchemaType(StrEnum):
    contribution = "contribution"
    table = "table"
    structure = "structure"


class LuxRegistry:
    """Registry of per-project schemas and cross-table validators.

    ``project_name`` must equal the project's MPContribs ``_id`` (the Projects
    Mongo collection primary key - a user-chosen ``ShortStr`` of 3-30
    characters). The registry does not verify that a project actually exists;
    that check belongs to the API server at runtime, which has the database connection.

    Prefer :meth:`validate` over fetching a schema with :meth:`get_schema` and
    validating it directly: ``validate`` runs schema validation *and* every
    applicable cross-object validator, so contribution- and table-spanning
    invariants cannot be silently skipped.
    """

    # project name -> schema type -> schema name -> schema class.
    projects: ClassVar[dict[str, dict[SchemaType, dict[str, type[BaseModel]]]]] = {}
    # project name -> cross-object validators (each gated by contribution/tables).
    validators: ClassVar[dict[str, list[_RegisteredValidator]]] = {}

    @classmethod
    def register_schema[SchemaT: BaseModel](
        cls,
        project_name: str,
        schema_type: SchemaType,
    ) -> Callable[[type[SchemaT]], type[SchemaT]]:
        """Register a schema class under ``project_name``/``schema_type``."""

        def decorator(subclass: type[SchemaT]) -> type[SchemaT]:
            key = subclass.__name__
            by_name = cls.projects.setdefault(project_name, {}).setdefault(
                schema_type, {}
            )
            existing = by_name.get(key)
            if existing is not None and existing is not subclass:
                raise ValueError(
                    f"{project_name!r} already has a {schema_type!r} schema "
                    + f"named {key!r} {existing.__name__}"
                )
            by_name[key] = subclass
            return subclass

        return decorator

    @classmethod
    def get_schemas(
        cls, project_name: str, schema_type: SchemaType
    ) -> dict[str, type[BaseModel]]:
        """Return the ``{name: schema}`` mapping for a project/type (may be empty)."""
        return dict(cls.projects.get(project_name, {}).get(schema_type, {}))

    @classmethod
    def get_schema(
        cls,
        project_name: str,
        schema_type: SchemaType,
        name: str | None = None,
    ) -> type[BaseModel]:
        """Return one registered schema class.

        Omit ``name`` when exactly one schema of that type is registered. With several registered, ``name``
        is required.
        Raises ``KeyError`` if nothing matches and ``ValueError`` if the lookup is ambiguous.
        """
        by_name = cls.projects.get(project_name, {}).get(schema_type, {})
        if not by_name:
            raise KeyError(
                f"no {schema_type!r} schema registered for project {project_name!r}"
            )
        if name is not None:
            try:
                return by_name[name]
            except KeyError as exc:
                raise KeyError(
                    f"project {project_name!r} has no {schema_type!r} schema "
                    + f"named {name!r}; available: {sorted(by_name)}"
                ) from exc
        if len(by_name) > 1:
            raise ValueError(
                f"project {project_name!r} has multiple {schema_type!r} schemas "
                + f"{sorted(by_name)}; pass name= to disambiguate"
            )
        return next(iter(by_name.values()))

    @classmethod
    def register_validator[ValidatorT: Validator](
        cls,
        project_name: str,
        *,
        contribution: str | type[BaseModel] | None = None,
        tables: str | type[BaseModel] | Iterable[str | type[BaseModel]] | None = None,
    ) -> Callable[[ValidatorT], ValidatorT]:
        """Register a cross-object validator, gated by contribution and/or tables.

        Declare at least one of:

        - ``contribution`` - a contribution schema (class or name); the validator
          runs when a submission of that contribution type is validated.
        - ``tables`` - a table schema (class or name) or several; the validator
          runs when all of those tables are present in the submission (any
          contribution type).
        """
        contribution_name = None if contribution is None else _schema_name(contribution)

        if tables is None:
            table_names: tuple[str, ...] = ()
        elif isinstance(tables, (str, type)):
            table_names = (_schema_name(tables),)
        else:
            table_names = tuple(_schema_name(table) for table in tables)

        if contribution_name is None and not table_names:
            raise ValueError("register_validator requires contribution= and/or tables=")

        project_schemas = cls.projects.get(project_name, {})
        if (
            contribution_name is not None
            and contribution_name
            not in project_schemas.get(SchemaType.contribution, {})
        ):
            raise ValueError(
                f"cannot register a validator for {project_name!r} contribution "
                + f"{contribution_name!r}: no such contribution schema is "
                + "registered; register it before its validator"
            )
        missing = [
            name
            for name in table_names
            if name not in project_schemas.get(SchemaType.table, {})
        ]
        if missing:
            raise ValueError(
                f"cannot register a validator for {project_name!r}: no such table "
                + f"schema(s) {missing}; register them before their validator"
            )

        def decorator(func: ValidatorT) -> ValidatorT:
            entry = _RegisteredValidator(func, contribution_name, table_names)
            entries = cls.validators.setdefault(project_name, [])
            if entry not in entries:
                entries.append(entry)
            return func

        return decorator

    @classmethod
    def get_validators(cls, project_name: str) -> list[Validator]:
        """Return every cross-object validator registered for a project."""
        return [entry.func for entry in cls.validators.get(project_name, [])]

    @classmethod
    def validate(
        cls,
        project_name: str,
        contribution: dict[str, Any] | BaseModel,
        contribution_name: str | None = None,
        tables: dict[str, list[dict[str, Any]]] | None = None,
        structures: dict[str, Any] | None = None,
    ) -> None:
        """Validate a full submission against a project's registered schemas.

        Validation happens in two phases:

        1. Schema validation. The ``contribution``  is validated
           against the project's ``contribution`` schema - ``contribution_name``
           selects which one when a project registers several, and may be omitted
           when exactly one is registered - and every provided table's rows are
           validated, row by row, against the table schema of the same name.
        2. Cross-object validation. Every registered validator whose requirements this
           submission satisfies is then run on the validated objects . Validators are
           additive - they express only the invariants pydantic cannot, never re-doing schema validation.

        ``tables`` is keyed by registered schema name (the pydantic class name),
        not parquet table/file name; mapping file names to schema names is the
        caller's responsibility. ``structures`` is passed through to validators
        unvalidated.
        """
        contribution_schema = cls.get_schema(
            project_name, SchemaType.contribution, name=contribution_name
        )
        contribution_obj = contribution_schema.model_validate(contribution)
        effective_name = contribution_schema.__name__

        by_name: dict[str, list[BaseModel]] = {}
        for name, rows in (tables or {}).items():
            table_schema = cls.get_schema(project_name, SchemaType.table, name=name)
            by_name[name] = [table_schema.model_validate(row) for row in rows]
        validated_tables = ValidatedTables(by_name)

        present = validated_tables.names()
        for entry in cls.validators.get(project_name, []):
            if entry.applies_to(effective_name, present):
                # Errors thrown in `func` are transparently raised here rather than wrapped in our own error
                entry.func(contribution_obj, validated_tables, structures or {})
