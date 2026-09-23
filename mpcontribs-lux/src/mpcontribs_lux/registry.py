from enum import StrEnum
from typing import Any, Callable, ClassVar

from pydantic import BaseModel

# A cross-table validator: given the validated contribution model, the attached
# tables (name -> list of row records), and any structures (name -> record),
# return True or raise on an invariant violation.
Validator = Callable[..., bool]


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
    validating it directly: ``validate`` always runs a project's declared
    cross-table validator, so contribution-spanning invariants cannot be
    silently skipped.
    """

    # project name -> schema type -> schema name -> schema class.
    projects: ClassVar[dict[str, dict[SchemaType, dict[str, type[BaseModel]]]]] = {}
    # (project name, contribution schema name) -> cross-table validator.
    validators: ClassVar[dict[tuple[str, str], Validator]] = {}

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
        contribution_name: str,
    ) -> Callable[[ValidatorT], ValidatorT]:
        """Register a cross-table validator for one contribution type.

        The validator is keyed by ``(project_name, contribution_name)`` where
        ``contribution_name`` is the class name of the ``contribution`` schema it
        validates, so a project may declare a distinct validator per contribution
        type. It is invoked by :meth:`validate` and must accept the validated
        contribution model, ``{table_name: rows}``, and ``{structure_name:
        record}``, returning True or raising on a violation.
        """

        def decorator(func: ValidatorT) -> ValidatorT:
            key = (project_name, contribution_name)
            existing = cls.validators.get(key)
            if existing is not None and existing is not func:
                raise ValueError(
                    f"{project_name!r} already has a cross-table validator for "
                    + f"contribution {contribution_name!r} ({existing.__name__})"
                )
            cls.validators[key] = func
            return func

        return decorator

    @classmethod
    def get_validator(
        cls, project_name: str, contribution_name: str
    ) -> Validator | None:
        """Return the cross-table validator for a contribution type, or None."""
        return cls.validators.get((project_name, contribution_name))

    @classmethod
    def validate(
        cls,
        project_name: str,
        contribution: dict[str, Any] | BaseModel,
        contribution_name: str | None = None,
        tables: dict[str, list[dict[str, Any]]] | None = None,
        structures: dict[str, Any] | None = None,
    ) -> bool:
        """Validate a full submission against a project's registered schemas.

        The ``contribution`` (main record) is validated against the project's
        ``contribution`` schema. ``contribution_name`` selects which one when a
        project registers several; it may be omitted when exactly one is
        registered.

        If the resolved contribution type has a declared cross-table validator,
        that validator is always run and owns validation of ``tables`` (and
        ``structures``). Otherwise each provided table's rows are validated,
        row by row, against the table schema registered under the same name.

        ``tables`` is keyed by registered schema name (the pydantic class name),
        parquet table name; mapping file names to schema names is the caller's responsibility.
        """
        contribution_schema = cls.get_schema(
            project_name, SchemaType.contribution, name=contribution_name
        )
        contribution_obj = contribution_schema.model_validate(contribution)
        effective_name = contribution_schema.__name__

        validator = cls.validators.get((project_name, effective_name))
        if validator is not None:
            return validator(contribution_obj, tables or {}, structures or {})

        for name, rows in (tables or {}).items():
            table_schema = cls.get_schema(project_name, SchemaType.table, name=name)
            for row in rows:
                table_schema.model_validate(row)
        return True
