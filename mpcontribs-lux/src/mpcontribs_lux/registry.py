from enum import StrEnum
from typing import Any, Callable

from pydantic import Field
from pydantic.dataclasses import dataclass


class SchemaType(StrEnum):
    contribution = "contribution"
    table = "table"
    structure = "structure"


@dataclass()
class LuxRegistry:
    _projects: dict[str, dict[SchemaType, Any]] = Field(default_factory=dict)

    @classmethod
    def register_schema(
        cls, project_name: str, schema_type: SchemaType
    ) -> Callable[..., None]:
        def decorator(subclass) -> Any:
            cls._projects[project_name][schema_type] = subclass
            return subclass

        return decorator
