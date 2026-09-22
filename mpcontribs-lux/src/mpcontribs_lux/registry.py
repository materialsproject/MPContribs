from enum import StrEnum
from typing import Any, Callable, ClassVar


class SchemaType(StrEnum):
    contribution = "contribution"
    table = "table"
    structure = "structure"


class LuxRegistry:
    # project name -> schema type -> schema name -> schema class.
    projects: ClassVar[dict[str, dict[SchemaType, dict[str, Any]]]] = {}

    @classmethod
    def register_schema(
        cls,
        project_name: str,
        schema_type: SchemaType,
    ) -> Callable[..., Any]:
        """Register a schema class under ``project_name``/``schema_type``."""

        def decorator(subclass) -> Any:
            key = subclass.__name__
            by_name = cls.projects.setdefault(project_name, {}).setdefault(
                schema_type, {}
            )
            existing = by_name.get(key)
            if existing is not None and existing is not subclass:
                raise ValueError(
                    f"{project_name!r} already has a {schema_type!r} schema "
                    f"named {key!r} ({existing.__name__}); pass a distinct "
                    f"`name=` to register {subclass.__name__}"
                )
            by_name[key] = subclass
            return subclass

        return decorator

    @classmethod
    def get_schemas(cls, project_name: str, schema_type: SchemaType) -> dict[str, Any]:
        """Return the ``{name: schema}`` mapping for a project/type (may be empty)."""
        return dict(cls.projects.get(project_name, {}).get(schema_type, {}))

    @classmethod
    def get_schema(
        cls,
        project_name: str,
        schema_type: SchemaType,
        name: str | None = None,
    ) -> Any:
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
                    f"named {name!r}; available: {sorted(by_name)}"
                ) from exc
        if len(by_name) > 1:
            raise ValueError(
                f"project {project_name!r} has multiple {schema_type!r} schemas "
                f"{sorted(by_name)}; pass name= to disambiguate"
            )
        return next(iter(by_name.values()))
